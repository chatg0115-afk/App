[app]

# App info
title = APK URL Extractor
package.name = urlextractor
package.domain = com.vishal

# Source
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,txt,json

# Version
version = 1.0
version.regex = __version__ = ['"](.*)['"]
version.filename = %(source.dir)s/main.py

# Requirements
requirements = python3,kivy==2.3.0,androguard==4.1.2,pillow==10.4.0,pycryptodome

# Permissions
android.permissions = INTERNET,READ_EXTERNAL_STORAGE,WRITE_EXTERNAL_STORAGE

# API levels
android.api = 33
android.minapi = 21

# Architecture
android.arch = arm64-v8a

# Orientation
orientation = portrait

# Fullscreen
fullscreen = 0

# Enable AndroidX
android.enable_androidx = True

# Gradle dependencies
android.gradle_dependencies = 
    androidx.appcompat:appcompat:1.6.1,
    androidx.core:core:1.12.0

# Buildozer settings
[buildozer]

# Log level
log_level = 1

# Build directory
build_dir = .buildozer

# Bin directory
bin_dir = ./bin

# Cache for CI
buildozer.cache_dir = .buildozer_cache
