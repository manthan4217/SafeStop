import os
import sys
import subprocess

def main():
    print("=======================================================================")
    print(" SAFESTOP AI -- AUTOMATED ANDROID APK GENERATOR")
    print("=======================================================================")
    print(" An official Android project directory has been initialized at:")
    print(f" {os.path.abspath('android')}\n")

    print(" Choose your preferred APK Generation Method:\n")
    print(" [1] Native Android Gradle Build (Local Project)")
    print("     Uses the included native Kotlin Android project in ./android")
    print(" [2] PWA Bubblewrap Package Build")
    print("     Converts hosted Flask web app into a Trusted Web Activity APK")
    print(" [3] Online 1-Click PWABuilder")
    print("     Package live app via https://www.pwabuilder.com")
    print("=======================================================================\n")

    choice = input("Enter option [1-3] (Default: 1): ").strip() or "1"

    if choice == "1":
        android_dir = os.path.abspath("android")
        print(f"\nBuilding Android APK from local project at '{android_dir}'...")
        gradlew = os.path.join(android_dir, "gradlew.bat" if sys.platform == "win32" else "gradlew")
        
        if os.path.exists(gradlew):
            subprocess.run([gradlew, "assembleDebug"], cwd=android_dir)
            apk_path = os.path.join(android_dir, "app", "build", "outputs", "apk", "debug", "app-debug.apk")
            if os.path.exists(apk_path):
                print(f"\nSUCCESS! APK generated successfully at:\n {apk_path}")
                return
        print("\nNote: To compile the local APK binary directly:")
        print("1. Open Android Studio -> Open Folder -> Select 'c:\\Users\\manth\\OneDrive\\Desktop\\SafeStop\\android'")
        print("2. Click Build -> Build APK(s). Your 'SafeStop.apk' will be generated instantly in android/app/build/outputs/apk/debug/\n")

    elif choice == "2":
        server_url = input("Enter your hosted HTTPS server URL (e.g. https://safestop-app.com): ").strip()
        if not server_url:
            print("Error: A valid HTTPS URL is required for Bubblewrap PWA build.")
            return
        print(f"\nInitializing Bubblewrap CLI build for {server_url}...")
        subprocess.run(["npx", "@bubblewrap/cli", "init", f"--manifest={server_url}/static/manifest.json"])
        subprocess.run(["npx", "@bubblewrap/cli", "build"])

    elif choice == "3":
        print("\nInstructions for 1-Click Online APK Download:")
        print("1. Deploy SafeStop to Render, Railway, or AWS to get an https:// URL.")
        print("2. Visit https://www.pwabuilder.com and paste your server URL.")
        print("3. Click 'Build My PWA' -> 'Android' -> 'Download Package' to get your instant .apk file!")

if __name__ == '__main__':
    main()
