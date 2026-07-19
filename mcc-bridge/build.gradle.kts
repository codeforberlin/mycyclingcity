plugins {
    java
}

group = "de.sailab.mycyclingcity"
version = findProperty("version") as String

java {
    toolchain.languageVersion.set(JavaLanguageVersion.of(21))
}

repositories {
    mavenCentral()
    maven("https://repo.papermc.io/repository/maven-public/")
    maven("https://jitpack.io")
}

dependencies {
    // Paper 26.1.x API requires Java 25 to resolve; compile against 1.21.11 API (Java 21).
    // Runtime target: Paper 26.1.2 server.
    compileOnly("io.papermc.paper:paper-api:1.21.11-R0.1-SNAPSHOT")
    compileOnly("com.github.MilkBowl:VaultAPI:1.7.1")
    compileOnly("net.luckperms:api:5.4")
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
    implementation("com.google.code.gson:gson:2.11.0")
    implementation("org.yaml:snakeyaml:2.2")
}

tasks.withType<JavaCompile> {
    options.encoding = "UTF-8"
    options.release.set(21)
}

tasks.processResources {
    filesMatching("plugin.yml") {
        expand("version" to project.version)
    }
}

tasks.jar {
    archiveBaseName.set("MCC-Bridge")
    // Bundle OkHttp + Gson (not provided by the server)
    from(
        configurations.runtimeClasspath.get().filter { it.name.endsWith("jar") }.map { zipTree(it) }
    )
    duplicatesStrategy = org.gradle.api.file.DuplicatesStrategy.EXCLUDE
}
