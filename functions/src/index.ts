import {initializeApp} from "firebase-admin/app";
import {getAuth} from "firebase-admin/auth";
import {getFirestore, FieldValue} from "firebase-admin/firestore";
import {getDatabase} from "firebase-admin/database";
import {HttpsError, onCall} from "firebase-functions/v2/https";
import {onDocumentCreated} from "firebase-functions/v2/firestore";

initializeApp();

const firestore = getFirestore();
const realtimeDatabase = getDatabase();
const auth = getAuth();

type Role = "user" | "driver" | "admin";

interface CallableContext {
  auth?: {
    uid: string;
    token: Record<string, unknown>;
  };
}

function requireAuth(context: CallableContext): string {
  if (!context.auth) {
    throw new HttpsError("unauthenticated", "Authentication is required.");
  }
  return context.auth.uid;
}

function requireRole(context: CallableContext, expectedRole: Role): string {
  const uid = requireAuth(context);
  if (context.auth?.token.role !== expectedRole) {
    throw new HttpsError("permission-denied", `Role ${expectedRole} is required.`);
  }
  return uid;
}

function requireString(value: unknown, fieldName: string): string {
  if (typeof value !== "string" || value.trim().length === 0) {
    throw new HttpsError("invalid-argument", `${fieldName} is required.`);
  }
  return value.trim();
}

function requireNumber(value: unknown, fieldName: string): number {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    throw new HttpsError("invalid-argument", `${fieldName} must be a finite number.`);
  }
  return value;
}

function optionalNumber(value: unknown, fallback: number): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function requireRoleValue(value: unknown): Role {
  const role = requireString(value, "role");
  if (role !== "user" && role !== "driver" && role !== "admin") {
    throw new HttpsError("invalid-argument", "role must be user, driver, or admin.");
  }
  return role;
}

export const bootstrapDemoRole = onCall(async (request) => {
  const uid = requireAuth(request);
  const role = requireRoleValue(request.data?.role);

  await auth.setCustomUserClaims(uid, {role});
  await firestore.collection("users").doc(uid).set({
    uid,
    role,
    displayName: request.auth?.token.name ?? null,
    email: request.auth?.token.email ?? null,
    avatarUrl: request.auth?.token.picture ?? null,
    isBlocked: false,
    createdAt: FieldValue.serverTimestamp(),
    updatedAt: FieldValue.serverTimestamp()
  }, {merge: true});

  if (role === "driver") {
    await firestore.collection("drivers").doc(uid).set({
      uid,
      name: request.auth?.token.name ?? "RouteFood Driver",
      vehicleType: "bike",
      rating: 5,
      online: false,
      currentAssignmentId: null,
      capacity: 1,
      status: "offline",
      updatedAt: FieldValue.serverTimestamp()
    }, {merge: true});
  }

  return {uid, role};
});

export const createUserOrder = onCall(async (request) => {
  const uid = requireRole(request, "user");
  const restaurantId = requireString(request.data?.restaurantId, "restaurantId");
  const dropoffLat = requireNumber(request.data?.dropoffLocation?.lat, "dropoffLocation.lat");
  const dropoffLng = requireNumber(request.data?.dropoffLocation?.lng, "dropoffLocation.lng");
  const items = Array.isArray(request.data?.items) ? request.data.items : [];

  if (items.length === 0) {
    throw new HttpsError("invalid-argument", "At least one item is required.");
  }

  const restaurant = await firestore.collection("restaurants").doc(restaurantId).get();
  if (!restaurant.exists) {
    throw new HttpsError("not-found", "Restaurant does not exist.");
  }

  let subtotal = 0;
  const normalizedItems = [];
  for (const item of items) {
    const itemId = requireString(item?.itemId, "items[].itemId");
    const quantity = Math.max(1, Math.floor(optionalNumber(item?.quantity, 1)));
    const menuItem = await firestore.collection("restaurants").doc(restaurantId).collection("menu_items").doc(itemId).get();
    if (!menuItem.exists || menuItem.data()?.available === false) {
      throw new HttpsError("invalid-argument", `Menu item ${itemId} is not available.`);
    }
    const price = optionalNumber(menuItem.data()?.price, 0);
    subtotal += price * quantity;
    normalizedItems.push({
      itemId,
      name: menuItem.data()?.name ?? itemId,
      price,
      quantity
    });
  }

  const deliveryFee = subtotal > 0 ? 15000 : 0;
  const total = subtotal + deliveryFee;
  const pickupLocation = restaurant.data()?.geo ?? null;
  const orderRef = firestore.collection("orders").doc();
  await orderRef.set({
    userId: uid,
    restaurantId,
    items: normalizedItems,
    pickupLocation,
    dropoffLocation: {lat: dropoffLat, lng: dropoffLng},
    status: "ORDER_CREATED",
    paymentMethod: request.data?.paymentMethod ?? "COD_DEMO",
    subtotal,
    deliveryFee,
    total,
    createdAt: FieldValue.serverTimestamp(),
    updatedAt: FieldValue.serverTimestamp(),
    demoScenarioId: request.data?.demoScenarioId ?? "hcm-default"
  });

  return {orderId: orderRef.id, status: "ORDER_CREATED"};
});

export const setDriverOnline = onCall(async (request) => {
  const uid = requireRole(request, "driver");
  const online = request.data?.online === true;
  const lat = requireNumber(request.data?.location?.lat, "location.lat");
  const lng = requireNumber(request.data?.location?.lng, "location.lng");

  await firestore.collection("drivers").doc(uid).set({
    uid,
    online,
    status: online ? "idle" : "offline",
    lastLocation: {lat, lng},
    lastHeartbeatAt: FieldValue.serverTimestamp(),
    updatedAt: FieldValue.serverTimestamp()
  }, {merge: true});

  await realtimeDatabase.ref(`driver_locations/${uid}`).set({
    uid,
    lat,
    lng,
    status: online ? "idle" : "offline",
    updatedAt: Date.now()
  });

  return {driverId: uid, online};
});

export const updateDriverLocation = onCall(async (request) => {
  const uid = requireRole(request, "driver");
  const lat = requireNumber(request.data?.lat, "lat");
  const lng = requireNumber(request.data?.lng, "lng");

  await realtimeDatabase.ref(`driver_locations/${uid}`).set({
    uid,
    lat,
    lng,
    heading: request.data?.heading ?? null,
    speed: request.data?.speed ?? null,
    accuracy: request.data?.accuracy ?? null,
    status: request.data?.status ?? "idle",
    updatedAt: Date.now()
  });

  await firestore.collection("drivers").doc(uid).set({
    lastLocation: {lat, lng},
    lastHeartbeatAt: FieldValue.serverTimestamp()
  }, {merge: true});

  return {ok: true};
});

export const driverAcceptAssignment = onCall(async (request) => {
  const uid = requireRole(request, "driver");
  const assignmentId = requireString(request.data?.assignmentId, "assignmentId");
  const assignmentRef = firestore.collection("assignments").doc(assignmentId);
  const assignment = await assignmentRef.get();

  if (!assignment.exists || assignment.data()?.driverUid !== uid) {
    throw new HttpsError("permission-denied", "Assignment is not available for this driver.");
  }

  await assignmentRef.update({
    status: "accepted",
    acceptedAt: FieldValue.serverTimestamp(),
    updatedAt: FieldValue.serverTimestamp()
  });

  return {assignmentId, status: "accepted"};
});

export const driverRejectAssignment = onCall(async (request) => {
  const uid = requireRole(request, "driver");
  const assignmentId = requireString(request.data?.assignmentId, "assignmentId");
  const assignmentRef = firestore.collection("assignments").doc(assignmentId);
  const assignment = await assignmentRef.get();

  if (!assignment.exists || assignment.data()?.driverUid !== uid) {
    throw new HttpsError("permission-denied", "Assignment is not available for this driver.");
  }

  await assignmentRef.update({
    status: "rejected",
    rejectedAt: FieldValue.serverTimestamp(),
    updatedAt: FieldValue.serverTimestamp()
  });

  return {assignmentId, status: "rejected"};
});

export const advanceDemoOrder = onCall(async (request) => {
  requireAuth(request);
  const orderId = requireString(request.data?.orderId, "orderId");
  const nextStatus = requireString(request.data?.nextStatus, "nextStatus");

  await firestore.collection("orders").doc(orderId).update({
    status: nextStatus,
    updatedAt: FieldValue.serverTimestamp()
  });

  return {orderId, status: nextStatus};
});

export const dispatchOrder = onDocumentCreated("orders/{orderId}", async (event) => {
  const orderId = event.params.orderId;
  const order = event.data?.data();
  if (!order || order.status !== "ORDER_CREATED") {
    return;
  }

  await firestore.collection("orders").doc(orderId).set({
    status: "ASSIGNING_DRIVER",
    dispatchRequestedAt: FieldValue.serverTimestamp(),
    updatedAt: FieldValue.serverTimestamp()
  }, {merge: true});

  const driverSnapshot = await firestore.collection("drivers")
    .where("online", "==", true)
    .where("status", "==", "idle")
    .limit(20)
    .get();

  if (driverSnapshot.empty) {
    await firestore.collection("orders").doc(orderId).set({
      status: "ASSIGNING_DRIVER",
      degradeReasons: ["no-online-driver"],
      updatedAt: FieldValue.serverTimestamp()
    }, {merge: true});
    return;
  }

  const dropoff = order.dropoffLocation ?? {lat: 10.7741, lng: 106.7038};
  let selectedDriver = driverSnapshot.docs[0];
  let selectedDistance = Number.MAX_VALUE;
  for (const driver of driverSnapshot.docs) {
    const location = driver.data().lastLocation ?? {lat: 10.7741, lng: 106.7038};
    const distance = distanceMeters(location.lat, location.lng, dropoff.lat, dropoff.lng);
    if (distance < selectedDistance) {
      selectedDriver = driver;
      selectedDistance = distance;
    }
  }

  const etaMin = Math.max(8, Math.round(selectedDistance / 350));
  const assignmentRef = firestore.collection("assignments").doc();
  await assignmentRef.set({
    orderIds: [orderId],
    driverId: selectedDriver.id,
    driverUid: selectedDriver.data().uid ?? selectedDriver.id,
    status: "assigned",
    pickupSequence: [order.restaurantId],
    dropoffSequence: [orderId],
    route: [],
    eta: {minutes: etaMin},
    risk: "fallback-medium",
    trafficProfile: "demo-hcm",
    weatherProfile: "light_rain",
    createdAt: FieldValue.serverTimestamp(),
    degradeReasons: ["nearest-driver-fallback"]
  });

  await firestore.collection("orders").doc(orderId).set({
    status: "DRIVER_ASSIGNED",
    assignedDriverId: selectedDriver.id,
    assignedDriverUid: selectedDriver.data().uid ?? selectedDriver.id,
    assignmentId: assignmentRef.id,
    etaMin,
    routeId: "fallback-" + assignmentRef.id,
    updatedAt: FieldValue.serverTimestamp(),
    degradeReasons: ["nearest-driver-fallback"]
  }, {merge: true});

  await firestore.collection("drivers").doc(selectedDriver.id).set({
    status: "assigned",
    currentAssignmentId: assignmentRef.id,
    updatedAt: FieldValue.serverTimestamp()
  }, {merge: true});
});

function distanceMeters(fromLat: number, fromLng: number, toLat: number, toLng: number): number {
  const earthRadiusMeters = 6371000;
  const dLat = (toLat - fromLat) * Math.PI / 180;
  const dLng = (toLng - fromLng) * Math.PI / 180;
  const a = Math.sin(dLat / 2) * Math.sin(dLat / 2)
    + Math.cos(fromLat * Math.PI / 180) * Math.cos(toLat * Math.PI / 180)
    * Math.sin(dLng / 2) * Math.sin(dLng / 2);
  return earthRadiusMeters * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}
