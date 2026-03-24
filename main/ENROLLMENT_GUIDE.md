# 📝 File-Based User Enrollment Guide (PYNQ-Z2)

## Overview

Since the PYNQ board runs the face recognition system **continuously** as a service, we use a **file-based approach** to request new user enrollments without stopping the main process.

---

## How It Works

### **1. Main Process Continuously Running**
```bash
# SSH into PYNQ board
ssh root@pynq

# Start face recognition (runs forever)
cd /home/root/face_auth
python main.py --mode recognition
```

### **2. Request Enrollment (From Another Terminal)**
While the main process is running, create an enrollment request file:

```bash
# On PYNQ board (in another SSH session)
cd /home/root/face_auth

# Create enrollment request
echo '{"username": "alice", "samples": 15}' > enroll_request.json
```

### **3. Main Process Detects Request**
The running Python process monitors for `enroll_request.json`:

```python
# In recognition loop:
if _check_enrollment_request():  # Looks for enroll_request.json
    username = _load_enrollment_request()  # Reads {"username": "alice"}
    run_enrollment(username)  # Captures 15 samples
    _delete_enrollment_request()  # Cleans up file
```

### **4. Enrollment Happens**
- Captures 15 face samples from camera
- Computes embeddings via FPGA
- Averages embeddings
- Stores in `data/users.json`
- **Returns to recognition mode automatically**

### **5. New User Ready**
Recognition mode resumes with the new user now in the database.

---

## File Format

**File:** `enroll_request.json`

```json
{
  "username": "alice",
  "samples": 15
}
```

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `username` | string | - | Unique user identifier (no spaces) |
| `samples` | int | 15 | Number of samples to capture (15 recommended) |

---

## Command-Line Examples

### **Enroll Alice (15 samples)**
```bash
echo '{"username": "alice"}' > enroll_request.json
```

### **Enroll Bob (20 samples)**
```bash
echo '{"username": "bob", "samples": 20}' > enroll_request.json
```

### **Monitor Progress**
```bash
# In another terminal, watch the logs
tail -f /tmp/face_recognition.log
```

Expected output:
```
[INFO] 📝 Enrollment request detected for user: alice
[INFO] Captured 1/15 samples
[INFO] Captured 2/15 samples
...
[INFO] Captured 15/15 samples
[INFO] ✅ Successfully enrolled alice
[INFO] ✅ Enrollment complete, resuming recognition...
```

---

## File Locations on PYNQ

```
/home/root/face_auth/
├── main.py                 # Main process (runs continuously)
├── enroll_request.json     # Enrollment request (created by user)
├── data/
│   └── users.json          # Database of enrolled users
└── logs/
    └── recognition.log     # Application logs
```

---

## Automation Scripts

### **Bash Script to Enroll Multiple Users**
```bash
#!/bin/bash
# enroll_users.sh

USERS=("alice" "bob" "charlie")
WORK_DIR="/home/root/face_auth"

for user in "${USERS[@]}"; do
    echo "Enrolling $user..."
    echo "{\"username\": \"$user\"}" > "$WORK_DIR/enroll_request.json"
    
    # Wait for enrollment to complete (adjust timeout as needed)
    sleep 30  # Wait for capture + processing
    
    # Verify completion
    if [ ! -f "$WORK_DIR/enroll_request.json" ]; then
        echo "✅ $user enrolled successfully"
    else
        echo "⚠️ Enrollment may have failed for $user"
    fi
done

echo "All enrollments complete!"
```

### **Python Script to Check Enrolled Users**
```python
import json

db_path = "/home/root/face_auth/data/users.json"

with open(db_path, 'r') as f:
    users = json.load(f)

print(f"Enrolled users: {list(users.keys())}")
print(f"Total: {len(users)} users")
```

---

## Troubleshooting

### **Enrollment Request Not Being Processed**
- Check if `enroll_request.json` exists: `ls -la enroll_request.json`
- Check main process log: `tail -f /tmp/face_recognition.log`
- Ensure JSON is valid: `python -m json.tool enroll_request.json`

### **Camera Not Detecting Face**
- Make sure camera is properly connected
- Check camera orientation and lighting
- Try moving closer/further from camera

### **File Not Deleted After Enrollment**
- Enrollment may have failed - check logs
- Manually delete: `rm enroll_request.json`
- Restart main process if stuck

### **Enrollment Hangs**
- No face detected for extended period
- Restart main process: `pkill -f "python main.py"`
- Run again with `--mode recognition`

---

## Integration with systemd (Optional)

To run face recognition automatically on boot:

### **Create Service File**
```bash
sudo nano /etc/systemd/system/face-auth.service
```

### **Service Configuration**
```ini
[Unit]
Description=PYNQ Face Authentication Service
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/home/root/face_auth
ExecStart=/usr/bin/python3 main.py --mode recognition --verbose
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### **Enable Service**
```bash
sudo systemctl daemon-reload
sudo systemctl enable face-auth.service
sudo systemctl start face-auth.service

# Check status
sudo systemctl status face-auth.service
```

---

## Summary

| Task | Method |
|------|--------|
| **Enroll new user** | Create `enroll_request.json` with username |
| **Check enrolled users** | Read `data/users.json` |
| **Stop enrollment** | Delete `enroll_request.json` (optional) |
| **Restart recognition** | Kill main process and rerun |
| **Monitor progress** | `tail -f /tmp/face_recognition.log` |

✅ **No need to stop the main process!**

