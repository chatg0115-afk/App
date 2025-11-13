[app]

# App info
title = APK URL Extractor
package.name = urlextractor
package.domain = com.extractor

# Source
source.dir = .
source.include_exts = py,png,jpg,kv,atlas

# Version
version = 1.0

# Requirements - UPDATED FOR 2025
requirements = python3==3.10,kivy==2.3.0,androguard==4.1.2,pillow==10.4.0,pycryptodome

# Permissions
android.permissions = INTERNET,READ_EXTERNAL_STORAGE,WRITE_EXTERNAL_STORAGE,MANAGE_EXTERNAL_STORAGE

# API levels - UPDATED FOR 2025
android.api = 34
android.minapi = 24
android.ndk = 25b
android.sdk = 34

# Accept SDK license
android.accept_sdk_license = True

# Architecture
android.archs = arm64-v8a

# Orientation
orientation = portrait

# Fullscreen
fullscreen = 0

# Enable AndroidX - IMPORTANT FOR 2025
android.enable_androidx = True
android.gradle_dependencies = androidx.core:core:1.12.0,androidx.appcompat:appcompat:1.6.1

# Gradle - UPDATED
android.gradle_version = 8.1.0
p4a.branch = master

# Bootstrap
p4a.bootstrap = sdl2

# Icon & Splash (optional)
#icon.filename = %(source.dir)s/icon.png
#presplash.filename = %(source.dir)s/presplash.png

# App theme
android.theme = @android:style/Theme.NoTitleBar

# Wakelock (optional)
# android.wakelock = False

# Meta-data
android.meta_data = com.google.android.gms.version=12451000

# Services (if needed)
# services = 

[buildozer]

# Log level (2 = detailed)
log_level = 2

# Warn on root
warn_on_root = 1

# Build directory
build_dir = ./.buildozer

# Bin directory  
bin_dir = ./bin

# Cache directory
# buildozer.cache_dir = .buildozer_cache
