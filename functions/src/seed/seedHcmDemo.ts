import {initializeApp} from "firebase-admin/app";
import {getFirestore, GeoPoint} from "firebase-admin/firestore";

initializeApp({projectId: process.env.GCLOUD_PROJECT || process.env.FIREBASE_PROJECT_ID || "routefood-demo"});

const firestore = getFirestore();

const restaurants = [
  {id: "q1-pho-nguyen-hue", name: "Pho Nguyen Hue", address: "Nguyen Hue, Ben Nghe, Quan 1", lat: 10.7741, lng: 106.7038, rating: 4.8, categories: ["pho", "breakfast"], prep: 12},
  {id: "bt-com-tam-landmark", name: "Com Tam Landmark", address: "Nguyen Huu Canh, Binh Thanh", lat: 10.7942, lng: 106.7218, rating: 4.7, categories: ["com tam", "lunch"], prep: 15},
  {id: "td-thao-dien-bento", name: "Thao Dien Bento", address: "Thao Dien, Thu Duc", lat: 10.8024, lng: 106.7331, rating: 4.6, categories: ["bento", "office"], prep: 18},
  {id: "q7-crescent-chicken", name: "Crescent Chicken", address: "Crescent Mall, Quan 7", lat: 10.7299, lng: 106.7187, rating: 4.5, categories: ["fried chicken", "dinner"], prep: 16},
  {id: "tb-airport-banh-mi", name: "Airport Banh Mi", address: "Cong Hoa, Tan Binh", lat: 10.8017, lng: 106.6533, rating: 4.4, categories: ["banh mi", "breakfast"], prep: 8},
  {id: "pn-tra-sua-phan-xich-long", name: "Phan Xich Long Milk Tea", address: "Phan Xich Long, Phu Nhuan", lat: 10.7984, lng: 106.6843, rating: 4.6, categories: ["milk tea", "snack"], prep: 10},
  {id: "q10-bun-bo-su-van-hanh", name: "Bun Bo Su Van Hanh", address: "Su Van Hanh, Quan 10", lat: 10.7721, lng: 106.6679, rating: 4.7, categories: ["bun bo", "dinner"], prep: 14},
  {id: "q3-hotpot-vo-van-tan", name: "Vo Van Tan Mini Hotpot", address: "Vo Van Tan, Quan 3", lat: 10.7756, lng: 106.6886, rating: 4.5, categories: ["hotpot", "rainy day"], prep: 20}
];

const menuTemplates = [
  {id: "signature", name: "Signature Combo", description: "Best seller combo for a fast HCMC delivery demo", price: 69000, category: "Popular"},
  {id: "classic", name: "Classic Meal", description: "Reliable daily meal with quick prep time", price: 52000, category: "Main"},
  {id: "drink", name: "Iced Tea", description: "Refreshing drink", price: 15000, category: "Drink"}
];

const drivers = [
  {id: "demo-driver-q1", name: "Minh Tran", lat: 10.776, lng: 106.704},
  {id: "demo-driver-bt", name: "An Nguyen", lat: 10.792, lng: 106.719},
  {id: "demo-driver-td", name: "Khoa Le", lat: 10.803, lng: 106.731},
  {id: "demo-driver-q7", name: "Linh Pham", lat: 10.731, lng: 106.717},
  {id: "demo-driver-tb", name: "Dat Vo", lat: 10.802, lng: 106.654}
];

const hotspots = [
  {id: "nguyen-huu-canh", name: "Nguyen Huu Canh", lat: 10.7942, lng: 106.7218, level: "severe", radius: 900, speedMultiplier: 1.55},
  {id: "cong-hoa", name: "Cong Hoa", lat: 10.8017, lng: 106.6533, level: "high", radius: 1100, speedMultiplier: 1.35},
  {id: "dien-bien-phu", name: "Dien Bien Phu", lat: 10.7901, lng: 106.7008, level: "high", radius: 1000, speedMultiplier: 1.3},
  {id: "nguyen-van-linh", name: "Nguyen Van Linh", lat: 10.7299, lng: 106.7187, level: "medium", radius: 1300, speedMultiplier: 1.2},
  {id: "xa-lo-ha-noi", name: "Xa Lo Ha Noi", lat: 10.8024, lng: 106.7331, level: "high", radius: 1400, speedMultiplier: 1.35}
];

async function seed() {
  const batch = firestore.batch();
  for (const restaurant of restaurants) {
    const restaurantRef = firestore.collection("restaurants").doc(restaurant.id);
    batch.set(restaurantRef, {
      name: restaurant.name,
      imageUrl: "",
      rating: restaurant.rating,
      address: restaurant.address,
      geo: new GeoPoint(restaurant.lat, restaurant.lng),
      categories: restaurant.categories,
      openHours: "07:00-22:00",
      avgPrepTimeMin: restaurant.prep,
      active: true,
      updatedAt: new Date()
    }, {merge: true});
    for (const item of menuTemplates) {
      batch.set(restaurantRef.collection("menu_items").doc(item.id), {
        ...item,
        imageUrl: "",
        popularityScore: item.id === "signature" ? 95 : 70,
        available: true,
        updatedAt: new Date()
      }, {merge: true});
    }
  }
  for (const driver of drivers) {
    batch.set(firestore.collection("drivers").doc(driver.id), {
      uid: driver.id,
      name: driver.name,
      vehicleType: "bike",
      plateNumber: "DEMO-" + driver.id.slice(-2).toUpperCase(),
      rating: 4.9,
      online: true,
      currentAssignmentId: null,
      capacity: 1,
      status: "idle",
      lastLocation: {lat: driver.lat, lng: driver.lng},
      lastHeartbeatAt: new Date(),
      updatedAt: new Date()
    }, {merge: true});
  }
  for (const hotspot of hotspots) {
    batch.set(firestore.collection("traffic_hotspots").doc(hotspot.id), {
      name: hotspot.name,
      center: new GeoPoint(hotspot.lat, hotspot.lng),
      radiusMeters: hotspot.radius,
      level: hotspot.level,
      activeTimeWindows: ["07:00-09:00", "17:00-19:30"],
      speedMultiplier: hotspot.speedMultiplier,
      updatedAt: new Date()
    }, {merge: true});
  }
  batch.set(firestore.collection("demo_config").doc("weather"), {
    status: "light_rain",
    etaMultiplier: 1.15,
    risk: "medium",
    updatedAt: new Date()
  }, {merge: true});
  await batch.commit();
  console.log(`Seeded ${restaurants.length} restaurants, ${drivers.length} drivers, and ${hotspots.length} hotspots.`);
}

seed().catch((error) => {
  console.error(error);
  process.exit(1);
});
