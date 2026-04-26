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

  const orderRef = firestore.collection("orders").doc();
  await orderRef.set({
    userId: uid,
    restaurantId,
    items,
    dropoffLocation: {lat: dropoffLat, lng: dropoffLng},
    status: "ORDER_CREATED",
    paymentMethod: request.data?.paymentMethod ?? "COD_DEMO",
    subtotal: request.data?.subtotal ?? 0,
    deliveryFee: request.data?.deliveryFee ?? 0,
    total: request.data?.total ?? 0,
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
  await firestore.collection("orders").doc(orderId).set({
    status: "ASSIGNING_DRIVER",
    dispatchRequestedAt: FieldValue.serverTimestamp(),
    updatedAt: FieldValue.serverTimestamp()
  }, {merge: true});
});
