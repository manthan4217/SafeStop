# SafeStop (SafeRide AI) — System Migration & Architectural Guide

This document outlines the architectural enhancements, schema migrations, multi-tenancy implementation, notification integration, security hardening, and biometric data governance introduced in **SafeStop**.

---

## 1. Schema Updates & Multi-Tenancy Architecture

### 1.1 Institution Scoping
- **`Institution` Model**: Serves as the primary tenant container (`name`, `slug`, `contact_email`, `plan_tier`, `invite_code`).
- **Denormalized `institution_id` Foreign Key**: Added to all entity models to guarantee strict tenant isolation and high query performance:
  - `User`, `Parent`, `Driver`, `Student`, `Bus`, `Route`, `Stop`, `Trip`, `Alert`, `AuditLog`.

### 1.2 Multi-Tenant Helper API (`app/tenancy.py`)
- `current_institution_id()`: Dynamically inspects `current_user` to retrieve active tenant ID.
- `verify_tenant_ownership(model_instance)`: Enforces cross-tenant authorization barriers by raising HTTP 403 Forbidden on illegal cross-institution access.

---

## 2. Real Outbound Notifications System (`app/notifications`)

### 2.1 Provider Abstraction Architecture
- **`BaseNotificationProvider`**: Abstract interface defining outbound delivery contracts.
- **`ConsoleProvider`**: Zero-dependency development provider logging outbound SMS and WhatsApp payloads to standard stdout/logger.
- **`TwilioProvider`**: Production provider delivering SMS & WhatsApp messages via Twilio REST API with automatic E.164 phone format validation.

### 2.2 Category & Priority Controls
- **OutboundSMS Categories**: High-priority alert categories (`BOARDING`, `ARRIVAL`, `SAFE_DROP`, `EMERGENCY`, `WRONG_BUS`) automatically dispatch external SMS/WhatsApp notifications to verified parents.
- **Phone Verification**: `User.phone_verified` boolean and `User.has_valid_phone()` method ensure notifications are dispatched only to valid phone numbers.

---

## 3. Security Hardening & Compliance

### 3.1 Production Environment Safeguards
- **Secret Enforcement**: App startup in `production` environment immediately fails with `ValueError` if `SECRET_KEY` or `WTF_CSRF_SECRET_KEY` are left unconfigured.
- **Rate Limiting**: `Flask-Limiter` integrated on authentication endpoints (`/auth/login`, `/auth/forgot-password`, `/auth/reset-password`) to prevent brute-force attacks.

### 3.2 Audit Logging & Manual Verification Controls
- **Manual Verification Audit**: Every manual driver override (`/driver/manual-verify`) logs an immutable `AuditLog` entry (`action='MANUAL_VERIFY_OVERRIDE'`).
- **Analytics Override Reporting**: Admin analytics dashboard (`/admin/analytics`) surfaces total attendance scans, manual override counts, and override percentage rates per driver and bus.

---

## 4. Biometric Data Governance & DSAR Compliance (`app/ai/governance.py`)

### 4.1 Parental Consent Tracking
- **`FaceProfile` Model**: Includes explicit consent tracking fields:
  - `parental_consent_given` (Boolean)
  - `consent_given_at` (DateTime)
  - `consent_given_by_user_id` (User ID)
  - `is_archived` & `archived_at` (Archival tracking)

### 4.2 Automated Retention Purge Job
- **`purge_expired_biometric_data(retention_days=365)`**: Hard-deletes facial embeddings and photo snapshots archived longer than the configured retention period.

### 4.3 Data Subject Access Request (DSAR) Endpoints
- **DSAR Export**: `GET /parent/dsar/export/<student_id>` generates full JSON export of student profile, biometric consent state, and attendance history.
- **Biometric Erasure**: `POST /parent/dsar/delete-biometrics/<student_id>` revokes consent, erases facial embedding vectors, and logs a compliance audit event (`DSAR_BIOMETRIC_DELETION`).

---

## 5. Deployment & CLI Commands

### Database Reset & Seeding
```bash
python manage_db.py reset
```

### Institutional Admin Creation CLI
```bash
python manage_db.py create-admin --email admin@kbp.edu --password SecurePass123! --full-name "Admin User" --institution-slug kbp-vashi
```

### Running Test Suite
```bash
python -m pytest
```
