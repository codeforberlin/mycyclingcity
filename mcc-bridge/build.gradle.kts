plugins {
    java
}

group = "de.sailab.mycyclingcity"
version = findProperty("version") as String

val toolchainVersion = (findProperty("toolchainVersion") as String?)?.toIntOrNull() ?: 21

java {
    // Default 21 (see README). Override with -PtoolchainVersion=25 when only JDK 25 is installed.
    toolchain.languageVersion.set(JavaLanguageVersion.of(toolchainVersion))
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
    compileOnly("com.github.Gypopo:EconomyShopGUI-API:1.10.1")
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
