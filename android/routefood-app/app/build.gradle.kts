plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
}

if (file("google-services.json").exists()) {
    apply(plugin = "com.google.gms.google-services")
}

android {
    buildFeatures {
        buildConfig = true
        compose = true
    }

    namespace = "com.routefood.app"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.routefood.app"
        minSdk = 24
        targetSdk = 35
        versionCode = 1
        versionName = "0.1.0"
        buildConfigField("String", "SUPABASE_URL", "\"${project.findProperty("SUPABASE_URL") ?: "https://nlceepwxgujzovebrjeo.supabase.co"}\"")
        buildConfigField("String", "SUPABASE_PUBLISHABLE_KEY", "\"${project.findProperty("SUPABASE_PUBLISHABLE_KEY") ?: "sb_publishable_j4S2TvBiqyyG1j3eOKuE_A_dbDoqzNM"}\"")
        buildConfigField("String", "VALHALLA_BASE_URL", "\"${project.findProperty("VALHALLA_BASE_URL") ?: "http://10.0.2.2:8002"}\"")
        buildConfigField("String", "GRAPHHOPPER_BASE_URL", "\"${project.findProperty("GRAPHHOPPER_BASE_URL") ?: "https://graphhopper.com/api/1"}\"")
        buildConfigField("String", "GRAPHHOPPER_API_KEY", "\"${project.findProperty("GRAPHHOPPER_API_KEY") ?: ""}\"")
        buildConfigField("String", "GRAPHHOPPER_PROFILE", "\"${project.findProperty("GRAPHHOPPER_PROFILE") ?: "car"}\"")
        buildConfigField("String", "OSRM_BASE_URL", "\"${project.findProperty("OSRM_BASE_URL") ?: "http://10.0.2.2:5000"}\"")
        buildConfigField("String", "PUBLIC_OSRM_BASE_URL", "\"${project.findProperty("PUBLIC_OSRM_BASE_URL") ?: "https://router.project-osrm.org"}\"")
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }
}

dependencies {
    val composeBom = platform("androidx.compose:compose-bom:2024.12.01")
    implementation(composeBom)
    androidTestImplementation(composeBom)

    implementation("androidx.activity:activity-compose:1.9.3")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.material:material-icons-extended")
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.ui:ui-tooling-preview")
    debugImplementation("androidx.compose.ui:ui-tooling")
    implementation("androidx.lifecycle:lifecycle-runtime-compose:2.8.7")
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.8.7")
    implementation("androidx.navigation:navigation-compose:2.8.5")
    implementation("io.coil-kt:coil-compose:2.7.0")
    implementation("org.maplibre.gl:android-sdk:11.8.0")
    implementation("org.java-websocket:Java-WebSocket:1.6.0")

    implementation(platform("com.google.firebase:firebase-bom:33.8.0"))
    implementation("com.google.firebase:firebase-auth")
    implementation("com.google.firebase:firebase-firestore")
    implementation("com.google.firebase:firebase-database")
    implementation("com.google.firebase:firebase-functions")
    implementation("com.google.firebase:firebase-storage")
    implementation("com.google.firebase:firebase-messaging")

    implementation("androidx.appcompat:appcompat:1.7.0")
    implementation("androidx.constraintlayout:constraintlayout:2.2.0")
    implementation("androidx.recyclerview:recyclerview:1.4.0")
    implementation("androidx.cardview:cardview:1.0.0")
    implementation("androidx.swiperefreshlayout:swiperefreshlayout:1.1.0")
    implementation("com.google.android.material:material:1.12.0")

    testImplementation("junit:junit:4.13.2")
    testImplementation("org.json:json:20250517")
}
