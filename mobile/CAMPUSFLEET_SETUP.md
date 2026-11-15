# CampusFleet Mobile

Expo + React Native customer app for the CampusFleet Python service. Register or log in first. Orders and account records are stored in the server's SQLite database. The phone can create and pay for a simulated delivery directly, or open an order created in the computer browser by the same account. Both devices must connect to the same running Python service and log in as the same user.

## Run on an Android emulator

1. Start the CampusFleet server from the project root: `python server.py`.
2. In this folder, run `npx expo start` and press `A` with an Android emulator running.
3. The default API URL is `http://10.0.2.2:8000`, the Android Emulator host alias for the computer.

## Run on a physical Android phone

1. Connect the phone and computer to the same private Wi-Fi network.
2. Start the Python server so it accepts LAN connections:

   ```powershell
   $env:CAMPUSFLEET_HOST = '0.0.0.0'
   python server.py
   ```

3. Copy `.env.example` to `.env` and set `EXPO_PUBLIC_API_URL` to the computer's private IPv4 address, for example `http://192.168.1.25:8000`.
4. Allow Python on the private network in Windows Firewall if prompted, restart Expo with `npx expo start`, and scan its QR code in Expo Go or the CampusFleet development build.

The current server uses simulated payments and simulated robot positions; the mobile client does not represent real payment or live robot telemetry. Account sessions on the phone are held in memory, so log in again after restarting the app. For a public deployment, use HTTPS and review authentication, data persistence, and payment handling first.

The desktop payment QR includes a random 30-minute ticket scoped to one order. It does not contain the account username or password. Anyone with the QR can view and pay that specific demo order until the ticket expires; do not expose QR images publicly.

The Android development build allows local HTTP for the classroom API. After changing this native setting, rebuild and reinstall the development app; restarting Metro alone does not change the Android manifest. Remove this allowance when switching the app to an HTTPS production API.
