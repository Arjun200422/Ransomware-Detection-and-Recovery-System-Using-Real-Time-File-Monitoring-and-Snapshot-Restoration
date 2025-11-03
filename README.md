# 🛡️ Ransomware Detection and Recovery System Using Real-Time File Monitoring and Snapshot Restoration

## 📖 Overview
This project is a **real-time ransomware detection and recovery system** implemented in Python.  
It continuously monitors directories for abnormal file activity, detects potential ransomware attacks based on **spike analysis** of file modifications, and allows users to **instantly restore original files** from secure snapshots.

The system also includes **Fernet-based encryption and decryption GUIs** that simulate ransomware activity, helping in testing and demonstrating the defense mechanism in action.

---

## ⚙️ Key Features
- 📂 **Real-Time Directory Monitoring** using `watchdog`  
- ⚡ **Spike Detection Heuristic** — detects sudden bursts of file changes typical of ransomware  
- 💾 **Automatic Snapshot and Restoration** to recover encrypted or deleted files  
- 🔐 **Fernet Encryption & Decryption GUIs** for simulation and testing  
- 📊 **Action Logging (CSV)** for event auditing and analysis  
- 🧰 **User Confirmation Alerts** to verify legitimate user activity before triggering recovery  

---

## 🧠 System Architecture
         ┌───────────────────────────────┐
         │  Encryption/Decryption GUIs   │
         │  (Simulate ransomware events) │
         └──────────────┬────────────────┘
                        │
                        ▼
            ┌──────────────────────┐
            │ Real-Time File Watch │
            │  (watchdog monitor)  │
            └───────────┬──────────┘
                        │
                        ▼
        ┌────────────────────────────────┐
        │Spike Detector & User Alert GUI │
        └──────────────┬─────────────────┘
                       │
                       ▼
          ┌────────────────────────────┐
          │ Snapshot & Restore Manager │
          │ (Recovery + Duplicate Save)│
          └────────────────────────────┘


---

## 🧩 Components Description

| File | Description |
|------|--------------|
| `crypto_utils.py` | Implements PBKDF2 key derivation and Fernet encryption/decryption helpers |
| `encrypt_gui.py` | GUI tool to encrypt selected files (simulating a ransomware attack) |
| `decrypt_gui.py` | GUI tool to decrypt files encrypted by the above script |
| `data_logger_gui_restore_alerts.py` | Main directory monitoring + spike detection + restoration GUI |
| `activity_restore_log.csv` | CSV log for all detected and restored file activities |
| `snapshots/` | Folder that stores original file copies for recovery |
| `duplicates/` | Folder where restored duplicate copies are stored |

---

## 🧪 How to Run

### 🔧 Step 1 — Clone the Repository
```bash
git clone https://github.com/Arjun200422/Ransomware-Detection-and-Recovery-System-Using-Real-Time-File-Monitoring-and-Snapshot-Restoration.git
cd Ransomware-Detection-and-Recovery-System-Using-Real-Time-File-Monitoring-and-Snapshot-Restoration

### 🔧 Step 1 — Clone the Repository
pip install watchdog cryptography

### 🖥️ Step 3 — Start Monitoring
python Ransomeware/data_logger_gui_restore_alerts.py --dir ./testing

### 💣 Step 4 — Simulate Ransomware Activity
python Ransomeware/encrypt_gui.py

### 🔐 Step 5 — Decrypt or Restore Files
python Ransomeware/decrypt_gui.py

### 📈 Output Demonstration

@ The monitor GUI displays:
@ Created / modified / deleted events
@ Spike detection alerts
@ User prompts for verification
@ Log entries in activity_restore_log.csv
