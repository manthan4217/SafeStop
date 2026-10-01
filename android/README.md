# 📱 SafeRide AI — Android Native APK Project (Android Studio)

This directory contains the official **Android Studio Project** for **SafeRide AI**. 

It packages the entire platform into a native Android APK app (`com.saferide.ai`), featuring native WebRTC camera permission handlers, GPS location tracking, hardware acceleration, and full-screen mobile operation for drivers and parents.

---

## 🛠️ How to Open & Build in Android Studio

### 1. Open Project in Android Studio
1. Launch **Android Studio**.
2. Click **Open** (or `File -> Open`).
3. Select the `android/` directory inside `SafeStop`:
   `c:\Users\manth\OneDrive\Desktop\SafeStop\android`
4. Android Studio will automatically index the project and sync Gradle dependencies.

---

### 2. Configure Backend Server URL
Open [`android/app/src/main/java/com/saferide/ai/MainActivity.kt`](file:///c:/Users/manth/OneDrive/Desktop/SafeStop/android/app/src/main/java/com/saferide/ai/MainActivity.kt):

```kotlin
// Change server URL as needed:
// "http://10.0.2.2:5000" -> Android Emulator loopback to host Flask server
// "http://192.168.1.100:5000" -> Physical phone connected on same Wi-Fi network
// "https://your-production-domain.com" -> Production cloud deployment
private val SERVER_URL = "http://10.0.2.2:5000"
```

---

### 3. Generate Android APK File
In Android Studio:
1. Go to top menu: **Build** ➔ **Build Bundle(s) / APK(s)** ➔ **Build APK(s)**.
2. Android Studio will compile the Kotlin code and generate:
   `android/app/build/outputs/apk/debug/app-debug.apk`
3. Click **locate** in the Android Studio notification popup to copy the APK file to your mobile phone.

---

## 🔒 Native Permissions Handled
- **Camera Access (`android.permission.CAMERA`)**: Automatically granted via `WebChromeClient.onPermissionRequest()` so the driver's phone camera scans student faces inside the native app without browser prompt interruptions.
- **GPS Location (`android.permission.ACCESS_FINE_LOCATION`)**: Enables real-time bus route deviation tracking and geofencing.
- **Audio (`android.permission.RECORD_AUDIO`)**: Enables Web Speech API driver voice callouts.
