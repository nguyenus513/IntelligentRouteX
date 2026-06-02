plugins {
    java
    id("org.springframework.boot") version "3.3.5"
    id("io.spring.dependency-management") version "1.1.6"
}

group = "com.routechain"
version = "0.1.0"

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(21))
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter")
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    implementation("org.springframework.kafka:spring-kafka")
    runtimeOnly("org.postgresql:postgresql:42.7.4")
    implementation("org.springframework.boot:spring-boot-configuration-processor")
    implementation("com.google.ortools:ortools-java:9.14.6206")
    implementation("com.fasterxml.jackson.dataformat:jackson-dataformat-yaml")
    implementation("jakarta.validation:jakarta.validation-api:3.1.0")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.kafka:spring-kafka-test")
}

tasks.withType<Test>().configureEach {
    useJUnitPlatform()
}
