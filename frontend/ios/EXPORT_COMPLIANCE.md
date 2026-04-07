# Perennia AI iOS App -- Export Compliance Documentation

**App Name:** PerenniaAI CRM Platform
**Bundle ID:** com.perenniaai.crm
**Document Version:** 1.0
**Last Updated:** 2026-04-07
**Author:** Engineering Team


## 1. Executive Summary

The Perennia AI iOS app sets `ITSAppUsesNonExemptEncryption` to `false` in Info.plist.
This document provides the technical justification for that setting by analyzing every
cryptographic operation in the app against the U.S. Bureau of Industry and Security (BIS)
Export Administration Regulations (EAR) and Apple's App Store export compliance requirements.

**Conclusion:** The `false` setting is correct. The app does not require an Encryption
Registration Number (ERN) or CCATS filing. All cryptographic functionality falls under
EAR exemptions, specifically Note 4 to Category 5 Part 2 (authentication, digital
signature, and data integrity) and the standard HTTPS/TLS exemption.


## 2. Apple's ITSAppUsesNonExemptEncryption Criteria

Apple requires developers to answer whether their app uses encryption that is NOT exempt
under U.S. export regulations. The key question is not "does your app use encryption?"
but rather "does your app use encryption that goes beyond what is exempt?"

### What Counts as Non-Exempt Encryption

An app uses non-exempt encryption if it:

1. Contains, incorporates, or calls custom encryption algorithms (proprietary ciphers)
2. Includes standard encryption algorithms (AES, RSA, etc.) used for confidentiality
   of user data in transit or at rest, where the encryption is NOT provided by the
   operating system or standard platform APIs
3. Implements VPN, end-to-end messaging encryption, or encrypted tunneling
4. Uses encryption to obscure or protect proprietary protocols

### What IS Exempt (EAR Category 5 Part 2 exemptions)

The following uses of encryption are exempt and do NOT require `true`:

- **HTTPS/TLS via OS APIs**: URLSession, WKWebView, and other Apple-provided networking
  frameworks that use the OS TLS stack (Note 4(b) -- authentication)
- **Authentication and digital signatures**: Token-based auth (JWT), PKCE code challenges,
  certificate validation, digital signatures (Note 4(a))
- **Hashing for data integrity**: SHA-256, SHA-1, MD5, FNV used for checksums, integrity
  verification, or fingerprinting (not for confidentiality)
- **OS-provided encryption at rest**: iOS Keychain, Data Protection API, FileVault
  (encryption provided by the platform, not the app)
- **DRM and copy protection**: Encryption used solely for content protection
- **Limited key length**: Symmetric keys <= 56 bits, asymmetric keys <= 512 bits (RSA)
  or 112 bits (ECC)

### The Critical Distinction

The distinction is between the **app** performing encryption vs. the **operating system**
performing encryption at the app's request via standard APIs. When an app calls
`URLSession` to make an HTTPS request, it is iOS/macOS that performs the TLS handshake
and encryption -- the app merely requests a secure connection. This is exempt.


## 3. Complete Inventory of Cryptographic Operations in the App

### 3.1 HTTPS/TLS Communication (EXEMPT)

| Component | Mechanism | Exempt? |
|-----------|-----------|---------|
| API calls to `api.perenniaai.com` | `URLSession` (Apple TLS stack) | Yes -- OS-provided |
| Web content from `app.perenniaai.com` | `WKWebView` (Apple TLS stack) | Yes -- OS-provided |
| Share extension API calls | `URLSession.shared` | Yes -- OS-provided |
| Pin failure reporting | `URLSession` ephemeral session | Yes -- OS-provided |

**Analysis:** All network communication uses Apple's URLSession or WKWebView, which
delegate TLS to the operating system's Secure Transport / Network.framework. The app
does not implement any custom TLS cipher suites, certificate handling beyond validation,
or encrypted tunnel protocols. App Transport Security (ATS) is enabled and enforces
HTTPS for both pinned domains.

**Relevant code:**
- `ShareNetworkService.swift` -- all `URLSession.shared.dataTask()` calls
- `CertificatePinning.swift` -- `URLSession` with custom delegate (TLS still handled by OS)
- `Info.plist` -- `NSAppTransportSecurity` configuration (HTTPS enforced)


### 3.2 Certificate Pinning with SHA-256 SPKI Hashing (EXEMPT)

| Operation | API Used | Purpose | Exempt? |
|-----------|----------|---------|---------|
| Extract public key from cert | `SecCertificateCopyKey()` | Read key material | Yes -- no encryption |
| SHA-256 hash of SPKI | `CC_SHA256()` via CommonCrypto | Identity verification | Yes -- authentication |
| Compare hash to pinned values | String comparison | Validate server identity | Yes -- not encryption |

**Analysis:** The certificate pinning implementation (`CertificatePinning.swift`) uses
Apple's CommonCrypto `CC_SHA256()` function to compute a hash of the server certificate's
Subject Public Key Info. This hash is then compared against hardcoded expected values.

This is explicitly **not encryption**. It is a one-way hash used for identity verification
(authentication). The SHA-256 operation:
- Does not encrypt or decrypt any data
- Does not protect confidentiality of any content
- Is used solely to verify that a server's certificate matches an expected fingerprint
- Falls squarely under Note 4 to Category 5 Part 2: "authentication" and "digital
  signature" uses are exempt

The `SecKeyCopyExternalRepresentation()` call extracts raw public key bytes for hashing
purposes only -- no encryption or decryption is performed with the key.

**Relevant code:**
- `CertificatePinning.swift` lines 142-208 (`extractSPKIHash()`)
- `CertificatePinning.swift` lines 252-337 (`handleServerTrust()`)


### 3.3 JWT Token Handling (EXEMPT)

| Operation | Location | Purpose | Exempt? |
|-----------|----------|---------|---------|
| Base64-decode JWT payload | `ShareNetworkService.swift` | Read token expiry | Yes -- not encryption |
| Send JWT in Authorization header | All API calls | Authentication | Yes -- OS handles TLS |
| Store JWT in Preferences/Keychain | `secureStorage.js`, App Group | Credential storage | Yes -- OS Keychain |

**Analysis:** The app reads JWT tokens but does not create, sign, or verify them. JWT
creation and RS256 signature verification happen entirely on the backend. The app only:
- Decodes the base64 payload to check the `exp` claim (line 409-426 of ShareNetworkService.swift)
- Sends the token as a bearer credential over HTTPS

This is authentication, not encryption. The token itself is not encrypted by the app.

**Relevant code:**
- `ShareNetworkService.swift` lines 409-426 (`isTokenExpired()`)
- `secureStorage.js` -- stores/retrieves tokens


### 3.4 XOR Obfuscation in Secure Storage (EXEMPT)

| Operation | Location | Purpose | Exempt? |
|-----------|----------|---------|---------|
| XOR cipher with derived key | `secureStorage.js` lines 148-174 | Obfuscate stored tokens | Yes -- see analysis |

**Analysis:** The `secureStorage.js` file implements a simple XOR cipher for obfuscating
sensitive data in Capacitor Preferences. The code comments explicitly state this is "not
AES" and is an "XOR cipher with key stretching, suitable for obfuscation-at-rest."

This is exempt for multiple reasons:
1. **XOR with a short repeating key is not considered strong encryption** under EAR.
   The key derivation uses simple byte mixing (not PBKDF2/scrypt/Argon2), and the
   XOR operation with a 32-byte repeating key provides no meaningful cryptographic
   security guarantee.
2. **The actual protection comes from the OS Keychain**, which stores the seed. The
   XOR layer is defense-in-depth obfuscation, not the primary security mechanism.
3. **On native platforms, truly sensitive data (biometric credentials) uses the OS
   Keychain directly** (classified as RESTRICTED), bypassing this code entirely.
4. **On web, it degrades to sessionStorage-based obfuscation**, which the code
   acknowledges provides "protection only against trivial localStorage scraping."

Even if this were classified as encryption, it would fall under the authentication
exemption (Note 4) since its sole purpose is protecting authentication credentials.

**Relevant code:**
- `frontend/src/services/secureStorage.js` lines 124-174


### 3.5 SHA-256 for PKCE Code Challenge (EXEMPT)

| Operation | Location | Purpose | Exempt? |
|-----------|----------|---------|---------|
| `crypto.subtle.digest('SHA-256', ...)` | `enterpriseSSO.js` line 71 | OAuth PKCE code challenge | Yes -- authentication |

**Analysis:** The enterprise SSO service uses the Web Crypto API's `SHA-256` digest to
generate PKCE (Proof Key for Code Exchange) code challenges for OAuth 2.0 flows. This
is a standard authentication protocol mechanism -- specifically, it prevents authorization
code interception attacks. It is a one-way hash, not encryption. This falls under the
authentication exemption.

**Relevant code:**
- `frontend/src/services/enterpriseSSO.js` line 71


### 3.6 FNV-1a Checksum for Tamper Detection (EXEMPT)

| Operation | Location | Purpose | Exempt? |
|-----------|----------|---------|---------|
| FNV-1a hash (32-bit) | `secureStorage.js` lines 180-192 | Data integrity checksum | Yes -- integrity check |

**Analysis:** A 32-bit FNV-1a hash is used as a checksum to detect tampering with stored
values. FNV-1a is not a cryptographic hash function and is not considered encryption under
any standard. It falls under the data integrity exemption.


### 3.7 iOS Keychain Access (EXEMPT)

| Operation | Location | Purpose | Exempt? |
|-----------|----------|---------|---------|
| Keychain read/write | App entitlements, secureStorage.js | Credential storage | Yes -- OS-provided |

**Analysis:** The app uses iOS Keychain Services (via the `keychain-access-groups`
entitlement) to store credentials. The encryption is performed entirely by the iOS
operating system's Keychain infrastructure. The app does not implement any keychain
encryption -- it calls system APIs.

**Relevant files:**
- `App.entitlements` / `App.entitlements.release` -- `keychain-access-groups`
- `PerenniaShare.entitlements` -- `keychain-access-groups`


### 3.8 Web Crypto API -- Environment Check Only (NOT ENCRYPTION)

| Operation | Location | Purpose | Exempt? |
|-----------|----------|---------|---------|
| `window.crypto.subtle.toString()` | `deviceIntegrity.js` line 134-135 | Feature detection | N/A -- not crypto use |

**Analysis:** The device integrity service checks for the *presence* of `crypto.subtle`
as a browser environment fingerprint. It does not call any cryptographic functions. This
is not a use of encryption.


## 4. What the App Does NOT Do

To be explicit about the absence of non-exempt encryption:

- **No custom encryption algorithms**: The app does not implement AES, RSA, ChaCha20,
  Blowfish, or any other standard or custom symmetric/asymmetric cipher.
- **No VPN or encrypted tunneling**: No IPsec, WireGuard, OpenVPN, or custom tunnel.
- **No end-to-end encryption**: Messages, documents, and data are not E2E encrypted.
- **No encrypted peer-to-peer communication**: No P2P protocol with encryption.
- **No encrypted local database**: No SQLCipher or encrypted CoreData/Realm.
- **No proprietary encrypted protocol**: All communication uses standard HTTPS.
- **No CryptoKit usage**: The app does not import or use Apple's CryptoKit framework.
- **No third-party crypto libraries**: No OpenSSL, libsodium, BouncyCastle, or similar.


## 5. Self-Classification Rationale

### BIS Classification

Under the Export Administration Regulations (15 CFR Part 740):

- **ECCN 5D002**: "Information Security" software that uses or performs cryptographic
  functions. This would apply if the app implemented non-exempt encryption.

- **EAR99**: Items not described by any ECCN entry. Apps that use only OS-provided
  HTTPS/TLS and exempt authentication cryptography fall under EAR99.

- **License Exception TSR (740.13(e))**: Even if the app were classified under 5D002,
  mass-market software distributed via the App Store qualifies for License Exception TSR
  after self-classification and a filing with BIS. However, this is not needed because
  the app qualifies under the exemptions in Note 4 to Category 5 Part 2.

### Applicable Exemptions

1. **Note 4(a) -- Authentication**: JWT tokens, certificate pinning, PKCE code challenges,
   and FNV checksums are all used for authentication or data integrity, not confidentiality.

2. **Note 4(b) -- Digital signature and data integrity**: SHA-256 hashing for SPKI pin
   validation and PKCE challenges are digital signature / integrity operations.

3. **OS-provided encryption**: All TLS/HTTPS encryption is performed by the iOS operating
   system via URLSession and WKWebView. Keychain encryption is performed by the iOS
   Secure Enclave. The app does not provide its own encryption implementation.

### Conclusion

The app's cryptographic usage is entirely within the scope of:
- Standard OS-provided HTTPS/TLS (exempt)
- Authentication mechanisms -- JWT, certificate pinning, PKCE (exempt under Note 4)
- Data integrity hashing -- SHA-256, FNV-1a (exempt under Note 4)
- OS Keychain for credential storage (OS-provided, exempt)
- XOR obfuscation for local storage (not meaningful encryption under EAR)


## 6. ERN / CCATS Requirements

### Is an Encryption Registration Number (ERN) Required?

**No.** An ERN (formerly CCATS) is required only when:

1. The app uses non-exempt encryption AND
2. The app is classified under ECCN 5D002 AND
3. The developer is self-classifying under License Exception ENC (740.17)

Since all cryptographic operations in this app are exempt under Note 4 to Category 5
Part 2, the app is classified as EAR99, and no ERN filing is required.

### Is a BIS Self-Classification Report Required?

**No.** The annual self-classification report (formerly SNAP-R filing) required under
Section 740.17(e) applies only to products classified under ECCN 5D002 that use
License Exception ENC. Since this app is EAR99, no reporting is required.

### Is a French Encryption Declaration Required?

**No.** France requires a declaration to ANSSI for products with their own cryptographic
means. Since this app relies exclusively on OS-provided cryptography (iOS TLS stack,
Keychain), no French declaration is required.


## 7. App Store Submission Checklist

When submitting to the App Store or uploading a build to App Store Connect, Apple asks
a series of export compliance questions. Here are the correct answers for this app:

### Question 1: "Does your app use encryption?"

**Answer: Yes**

The app makes HTTPS calls and uses iOS Keychain. Apple defines "encryption" broadly.

### Question 2: "Does your app qualify for any of the exemptions provided in Category 5, Part 2 of the U.S. Export Administration Regulations?"

**Answer: Yes**

All encryption usage is exempt:
- HTTPS/TLS via OS APIs (standard platform networking)
- SHA-256 for authentication (certificate pinning, PKCE)
- iOS Keychain (OS-provided credential storage)

### Question 3: "Does your app implement any proprietary encryption algorithms or use encryption other than that provided by the iOS platform?"

**Answer: No**

The XOR obfuscation in secureStorage.js is not a cryptographic algorithm under EAR.
CommonCrypto CC_SHA256 is an Apple-provided API (part of the iOS SDK), not a custom
implementation.

### Question 4: "Is your app available for sale in France?"

**Answer: Yes** (if distributing in France)

No additional French ANSSI declaration is needed because the app uses only OS-provided
cryptographic services.

### Info.plist Setting

```xml
<key>ITSAppUsesNonExemptEncryption</key>
<false/>
```

This setting is **correct** and should remain `false`. Setting this key to `false` in
Info.plist bypasses the manual export compliance questionnaire in App Store Connect,
streamlining the submission process.


## 8. Summary of Crypto-Related Source Files

| File | Crypto Operations | Classification |
|------|-------------------|----------------|
| `ios/App/App/CertificatePinning.swift` | CC_SHA256 (CommonCrypto), SecCertificateCopyKey, SecKeyCopyExternalRepresentation | Exempt -- authentication |
| `ios/App/App/Info.plist` | ITSAppUsesNonExemptEncryption declaration | N/A -- metadata |
| `ios/App/App/App.entitlements` | keychain-access-groups | Exempt -- OS Keychain |
| `ios/App/App/App.entitlements.release` | keychain-access-groups | Exempt -- OS Keychain |
| `ios/App/PerenniaShare/PerenniaShare.entitlements` | keychain-access-groups | Exempt -- OS Keychain |
| `ios/App/PerenniaShare/ShareNetworkService.swift` | URLSession HTTPS, JWT base64 decode | Exempt -- OS TLS, auth |
| `src/services/secureStorage.js` | XOR obfuscation, FNV-1a checksum | Exempt -- not meaningful encryption |
| `src/services/enterpriseSSO.js` | crypto.subtle.digest SHA-256 (PKCE) | Exempt -- authentication |
| `src/services/deviceIntegrity.js` | crypto.subtle feature detection only | N/A -- no crypto performed |


## 9. Regulatory References

- **EAR 15 CFR Part 730-774**: U.S. Export Administration Regulations
- **Category 5 Part 2**: "Information Security" -- defines controlled encryption items
- **Note 4 to Category 5 Part 2**: Exemptions for authentication, digital signature,
  data integrity, and access control
- **Supplement No. 3 to Part 740**: Self-classification reporting requirements
- **License Exception ENC (740.17)**: For mass-market encryption software
- **Apple Developer Documentation**: "Complying with Encryption Export Regulations"
  (https://developer.apple.com/documentation/security/complying_with_encryption_export_regulations)
- **BIS Encryption FAQ**: https://www.bis.doc.gov/index.php/policy-guidance/encryption


## 10. Review Schedule

This document should be reviewed and updated when:

- New cryptographic operations are added to the app
- Third-party SDKs with encryption are integrated (e.g., Signal Protocol, E2E messaging)
- The app begins using CryptoKit, OpenSSL, or any custom encryption library
- BIS or Apple changes export compliance requirements
- The app adds VPN, encrypted tunneling, or E2E encryption features

**Next scheduled review:** Before each major App Store submission or when crypto-related
code changes are merged.
