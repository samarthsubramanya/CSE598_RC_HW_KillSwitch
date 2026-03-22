# Quick Start Guide

Get up and running with the Face Authentication System in 5 minutes.

## 1️⃣ Install Dependencies

```bash
cd reference
pip install -r requirements.txt
```

Or use the setup script:
```bash
python setup.py
```

## 2️⃣ Verify Setup

Check if everything is working:
```bash
python -c "import cv2; import numpy; print('✅ Ready to run')"
```

## 3️⃣ Run the Application

### Interactive Mode (Recommended for first-time)
```bash
python main.py
```

You'll see a menu:
```
=== Face Authentication System ===
1. Start recognition
2. Enroll new user
3. List users
4. Delete user
5. Clear database
6. Adjust settings
0. Exit

Choose option:
```

### Direct Recognition
```bash
python main.py --mode recognition
```

### Enroll a User
```bash
python main.py --mode enroll --user "your_name"
```

## 🎯 Typical First-Time Workflow

```bash
# 1. Start system
python main.py

# 2. Choose option 2 (Enroll)
# 3. Enter your name
# 4. Move face around, collect 15 samples
# 5. Back to menu, choose option 1 (Recognition)
# 6. Stand in front of camera
# 7. Watch system recognize you! ✅
```

## ⚙️ Command-Line Options

```bash
# Use IP camera instead of webcam
python main.py --camera "http://192.168.1.100:8080/video"

# Adjust similarity threshold (lower = more permissive, 0.0-1.0)
python main.py --threshold 0.55

# Run in headless mode (no GUI, console output only)
python main.py --headless

# Combine options
python main.py --mode recognition --threshold 0.6 --headless
```

## 🎮 Keyboard Shortcuts (During Recognition)

| Key | Action |
|-----|--------|
| `q` | Quit |
| `e` | Enroll new user |
| `l` | List enrolled users |
| `d` | Delete user |
| `c` | Clear database |

## 📊 What to Expect

### CPU-based Performance:
- **FPS**: 5-10 (on typical laptop)
- **Latency**: 100-300ms per frame
- **Memory**: ~500MB

### Accuracy:
- Works well with frontal faces
- Affected by lighting conditions
- Multiple enrollment samples improve accuracy

## 🔧 Troubleshooting

### Camera not detected?
```bash
# Try different camera index
python main.py --camera 1
python main.py --camera 2
```

### Application crashes?
- Check OpenCV installation: `python -c "import cv2; print(cv2.__version__)"`
- Try `pip install --upgrade opencv-python`

### Recognition not working?
- Enroll with more samples
- Try lower similarity threshold: `--threshold 0.55`
- Check lighting conditions

### Very slow?
- Run in headless mode: `--headless`
- Use lower resolution (edit `camera.py` if needed)

## 📁 File Organization

```
reference/
├── data/
│   └── users.json          ← Stored enrollments (auto-created)
├── models/
│   └── nn4.small2.v1.t7    ← Pretrained model (optional)
├── *.py                    ← Python modules
└── README.md               ← Full documentation
```

## 🏃 Next Steps After Running

1. ✅ Test recognition with your face
2. ✅ Enroll a family member
3. ✅ Adjust thresholds for your environment
4. ✅ Test with different lighting
5. ✅ Read ARCHITECTURE.md to understand the system
6. ✅ When ready, port to PYNQ-Z2

## 📚 Learning Resources

- `README.md` - Full feature documentation
- `ARCHITECTURE.md` - Technical deep dive
- `setup.py` - Automated setup helper
- `PLAN.md` - Original project specification

## 🚀 Performance Tips

- **Better accuracy**: Enroll with more samples (20+)
- **Faster speed**: Run in headless mode
- **Better FPS**: Use lower camera resolution
- **Less latency**: Use GPU-accelerated OpenCV build (if available)

## ⚡ Quick Validation Checklist

After setup, verify:
- [ ] `python main.py` runs without errors
- [ ] Camera detected (can see video feed)
- [ ] Can enroll yourself
- [ ] Recognition works on your face
- [ ] Can recognize other people
- [ ] Hysteresis prevents flicker
- [ ] Settings menu works
- [ ] Database persists across runs

---

**You're ready to go! 🎉**

For detailed usage, see [README.md](README.md) and [ARCHITECTURE.md](ARCHITECTURE.md).
