# 🚌 SafeRide AI — School & College Student Live Bus Tracking & Parent Safety System

**SafeRide AI / SafeStop** is an enterprise-grade, web-based transportation tracking and safety management platform specifically designed for **school and college students and their parents** who use institutional bus services.

> ⚠️ **100% Software-Only Architecture — Zero Hardware Dependency**
> SafeRide AI requires **NO specialized hardware**, NO RFID readers, NO card scanners, NO Arduino/ESP32 microcontrollers, and **NO smartphones or devices for students**. 
> The platform operates strictly through responsive web software running on the driver's standard mobile browser and cloud/Python backend servers.

---

## 🌟 Core Value Proposition for Parents & Students

SafeRide AI gives parents full peace of mind by answering four key questions in real-time:
> **WHO is travelling + WHICH BUS they are travelling in + WHERE the bus is right now + WHETHER your child has safely boarded/arrived.**

---

## 👨‍👩‍👧 Key Features for Parents

1. **Private Live Child Tracking**
   - Parents log in to view **only their child's live location**, assigned bus route, and real-time movement on an interactive map.
   - Includes a custom **`🧒 [Child Name]` Live Pin** that animates along the route.

2. **Real-Time Safety Statuses**
   - **`📍 Waiting at Pickup Stop`**: Child is registered at their designated pickup stop.
   - **`🧒🚌 On Board Bus`**: Facial AI verifies when the student boards the bus; location tracks the live moving vehicle.
   - **`🏠 Safely Dropped`**: Child arrives at their drop destination.

3. **1-Tap Safe Drop Arrival Confirmation**
   - When the bus reaches the student's drop stop, the parent receives an instant notification to confirm receipt (`[ Child Received ]`).

4. **Parent ETA Proximity Alerts & Geo-Fenced Stop Triggers**
   - Live distance & ETA engine monitors bus GPS position in real-time.
   - Automatically dispatches `"🚌 Bus is 500m (~3 mins) away from stop"` alerts as the bus approaches.
   - Customizable proximity alert thresholds (250m, 500m, 1000m).

5. **Parent Leave / Absence Request Portal**
   - Log single or multi-day leave/sick requests directly from the parent dashboard.
   - Automatically marks students as `[ 🤒 ON LEAVE (Parent Verified) ]` on driver rosters.

---

## 🏛️ Multi-Tenancy Architecture (Institutional Isolation)

SafeStop supports multiple school/college institutions natively (`kbp-vashi`, `st-xaviers`).
- **Strict Data Scoping**: All database models (`User`, `Student`, `Driver`, `Bus`, `Route`, `Trip`, `Alert`, `AuditLog`) are institution-scoped.
- **Cross-Tenant Guardrails**: Automatic authorization checks reject illegal cross-tenant data requests.
- **Parent Self-Registration**: Parents can register directly using their school's unique `invite_code` (`KBP2026`, `STX2026`).

---

## 📱 Real Outbound Notifications (SMS & WhatsApp Integration)

SafeStop features an extensible notification delivery system:
- **Twilio Provider (`TwilioProvider`)**: Real SMS and WhatsApp messages delivered to parents for high-priority alerts (`BOARDING`, `ARRIVAL`, `SAFE_DROP`, `EMERGENCY`, `WRONG_BUS`).
- **Console Provider (`ConsoleProvider`)**: Zero-dependency development provider logging outbound SMS and WhatsApp payloads to standard output.
- **Fault-Tolerant Delivery**: Outbound API failures log warnings without interrupting critical attendance workflows.

---

## 🔒 Security Hardening & Rate Limiting

- **Production Environment Secrets Enforcement**: Application startup fails safely if default/insecure keys are used in `production`.
- **Rate Limiting**: `Flask-Limiter` protects authentication routes (`/auth/login`, `/auth/forgot-password`, `/auth/reset-password`) against brute-force attacks.
- **Manual Verification Auditing**: All driver manual attendance overrides create immutable `AuditLog` entries (`action='MANUAL_VERIFY_OVERRIDE'`) and surface override rates per driver/bus on the admin analytics dashboard.

---

## 🛡️ Biometric Data Governance & DSAR Compliance

- **Parental Consent Tracking**: Biometric face profile vectors are stored only with explicit parental consent.
- **Data Subject Access Request (DSAR)**: Parents can export full attendance & biometric consent records (`/parent/dsar/export/<student_id>`) or request complete face vector erasure (`/parent/dsar/delete-biometrics/<student_id>`).
- **Automated Data Retention Purge**: Background purge job (`purge_expired_biometric_data(retention_days=365)`) automatically hard-deletes face vectors archived longer than the retention window.

---

## 🚀 Quick Start Guide

### 1. Requirements
- Python 3.10+
- Modern Web Browser (Chrome, Edge, Safari, Firefox)

### 2. Run Application
```bash
python run.py
```
*Note: The application auto-detects and preserves existing user database records across server restarts.*

Open **http://127.0.0.1:5000** in your browser.

### 3. Database Management & Migrations
SafeStop uses Flask-Migrate (Alembic) for schema migrations:
```bash
flask db upgrade                                  # Apply database migrations to production/local DB
python manage_db.py status                        # View real-time database counts
python manage_db.py seed                          # Seed demo dataset (KBP College Vashi)
python manage_db.py create-admin --email <email>  # Create admin account
```
*Note: `flask db upgrade` replaces `db.create_all()` for environments with persistent data.*

### 4. Run Automated Test Suite
Execute unit tests using pytest:
```bash
python -m pytest
```
*Passes 18 automated test cases covering DB init, auth, wrong-bus detection, parent absence, driver telemetry, and parent proximity alerts.*

---

## 🔑 Stored Database Credentials

The database (`saferide.db`) is pre-populated with ready-to-use accounts:

### 👑 System Administrator (College/School Admin)
- **Email / ID**: `admin@saferide.ai`
- **Password**: `admin123`
- **Role**: Institutional Transport Director / Admin
- **Access URL**: [http://127.0.0.1:5000/auth/login](http://127.0.0.1:5000/auth/login)
- **Features**: Fleet Control Center, AI Risk Analytics, Add/Manage Buses, Drivers, Routes & Students.

### 🚘 Bus Driver Account
- **Email / ID**: `driver1@saferide.ai`
- **Password**: `driver123`
- **Role**: Official Bus Driver (BUS-05)
- **Access URL**: [http://127.0.0.1:5000/auth/login](http://127.0.0.1:5000/auth/login)
- **Features**: Start/End Trip, AI Facial Camera Verification, Live GPS Broadcast, SOS Alert.

### 👪 Student Parent Accounts
- **Password for all Parents (`parent1@saferide.ai` to `parent15@saferide.ai`)**: `parent123`
- **Features**: Track Child Live Location, Safe Drop Arrival Confirmation, Instant Boarding Alerts.

---

## 🎓 Stored Student Dataset — Karmaveer Bhaurao Patil (KBP) College, Vashi

All 15 students have registered daily commutes from **Home ➔ KBP College Vashi (Morning)** and **KBP College Vashi ➔ Home (Evening)**:

| # | Student Name | Roll Number | Department / Grade | Home Pickup & Drop Stop | Destination | Bus | Parent Login |
|---|---|---|---|---|---|---|---|
| 1 | **Manthan Patil** | `KBP-2026-CS501` | B.Sc Computer Science (3rd Yr) | Sector 17 Vashi Plaza | KBP College Main Gate | BUS-05 | `parent1@saferide.ai` |
| 2 | **Ananya Sharma** | `KBP-2026-102` | B.Com (1st Yr) | Sector 9 Vashi Market | KBP College Main Gate | BUS-05 | `parent2@saferide.ai` |
| 3 | **Rohan Verma** | `KBP-2026-103` | B.Sc IT (3rd Yr) | Kopar Khairane Station Circle | KBP College Main Gate | BUS-05 | `parent3@saferide.ai` |
| 4 | **Ishita Gupta** | `KBP-2026-104` | BBA (2nd Yr) | CBD Belapur Station | KBP College Main Gate | BUS-08 | `parent4@saferide.ai` |
| 5 | **Aarav Deshmukh** | `KBP-2026-105` | B.Sc Data Science (2nd Yr) | Nerul LP Junction (Sec 21) | KBP College Main Gate | BUS-08 | `parent5@saferide.ai` |
| 6 | **Sanya Kulkarni** | `KBP-2026-106` | M.Sc CS (1st Yr) | Juinagar Station West | KBP College Main Gate | BUS-08 | `parent6@saferide.ai` |
| 7 | **Aditya Shinde** | `KBP-2026-107` | B.Tech AI (1st Yr) | Sector 17 Vashi Plaza | KBP College Main Gate | BUS-05 | `parent7@saferide.ai` |
| 8 | **Riya More** | `KBP-2026-108` | B.A. Mass Comm (3rd Yr) | Sector 9 Vashi Market | KBP College Main Gate | BUS-05 | `parent8@saferide.ai` |
| 9 | **Kabir Joshi** | `KBP-2026-109` | B.Sc Biotech (2nd Yr) | Kopar Khairane Station Circle | KBP College Main Gate | BUS-05 | `parent9@saferide.ai` |
| 10 | **Tanvi Bhosale** | `KBP-2026-110` | B.Com Accounting (1st Yr) | CBD Belapur Station | KBP College Main Gate | BUS-08 | `parent10@saferide.ai` |
| 11 | **Yash Pawar** | `KBP-2026-111` | B.Sc MicroBiology (3rd Yr) | Nerul LP Junction (Sec 21) | KBP College Main Gate | BUS-08 | `parent11@saferide.ai` |
| 12 | **Prisha Nambiar** | `KBP-2026-112` | BMS Management (2nd Yr) | Juinagar Station West | KBP College Main Gate | BUS-08 | `parent12@saferide.ai` |
| 13 | **Siddharth Chavan** | `KBP-2026-113` | B.Sc Cyber Security (1st Yr) | Sector 17 Vashi Plaza | KBP College Main Gate | BUS-05 | `parent13@saferide.ai` |
| 14 | **Neha Thorat** | `KBP-2026-114` | M.Com Finance (2nd Yr) | Sector 9 Vashi Market | KBP College Main Gate | BUS-05 | `parent14@saferide.ai` |
| 15 | **Varun Kadam** | `KBP-2026-115` | B.Sc Chemistry (3rd Yr) | Kopar Khairane Station Circle | KBP College Main Gate | BUS-05 | `parent15@saferide.ai` |

---

## 🛠️ Software Stack

- **Backend**: Python 3, Flask, SQLAlchemy ORM, Flask-Login, Werkzeug Security
- **Database**: SQLite (Zero-setup local execution) / Relational database schema
- **AI & Facial Recognition**: OpenCV, NumPy, Scikit-Learn (Cosine Similarity Feature Matching)
- **Maps & Live Tracking**: Leaflet.js, OpenStreetMap, HTML5 Geolocation API
- **Frontend & UI**: HTML5, CSS3, JavaScript ES6, Bootstrap 5, Chart.js, Animate.css
