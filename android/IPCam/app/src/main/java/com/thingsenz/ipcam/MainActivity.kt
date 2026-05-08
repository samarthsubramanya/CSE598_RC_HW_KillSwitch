package com.thingsenz.ipcam

import android.Manifest
import android.annotation.SuppressLint
import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.graphics.Rect
import android.os.Bundle
import android.util.Log
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.camera.core.*
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Camera
import androidx.compose.material.icons.filled.Cameraswitch
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.PersonAdd
import androidx.compose.material.icons.filled.Videocam
import androidx.compose.material.icons.filled.VideocamOff
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalLifecycleOwner
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.content.ContextCompat
import com.google.mlkit.vision.common.InputImage
import com.google.mlkit.vision.face.FaceDetection
import com.google.mlkit.vision.face.FaceDetectorOptions
import com.thingsenz.ipcam.ui.theme.IPCamTheme
import kotlinx.coroutines.delay
import java.io.ByteArrayOutputStream
import java.net.NetworkInterface
import java.util.concurrent.Executors
import kotlin.math.abs

data class FaceTelemetry(val boundingBox: Rect, val eulerY: Float, val imageWidth: Int, val imageHeight: Int)

class MainActivity : ComponentActivity() {

    private lateinit var cameraServer: CameraServer
    private val serverPort = 8080

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        cameraServer = CameraServer(serverPort)

        val requestPermissionLauncher = registerForActivityResult(
            ActivityResultContracts.RequestPermission()
        ) { isGranted: Boolean ->
            if (isGranted) {
                setContent { MainScreen(cameraServer) }
            } else {
                setContent {
                    Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                        Text("Camera permission is required.")
                    }
                }
            }
        }

        enableEdgeToEdge()

        if (ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED) {
            setContent { MainScreen(cameraServer) }
        } else {
            setContent {
                IPCamTheme {
                    Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                        Text("Requesting camera permission...")
                    }
                }
            }
            requestPermissionLauncher.launch(Manifest.permission.CAMERA)
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        if (cameraServer.isAlive) {
            cameraServer.stop()
        }
    }
}

@Composable
fun MainScreen(cameraServer: CameraServer) {
    var isServerRunning by remember { mutableStateOf(false) }
    var urls by remember { mutableStateOf<List<String>>(emptyList()) }

    var showNameDialog by remember { mutableStateOf(false) }
    var registrationName by remember { mutableStateOf("") }
    var registrationMode by remember { mutableStateOf(false) }

    var detectedFaces by remember { mutableStateOf<List<FaceTelemetry>>(emptyList()) }
    var lensFacing by remember { mutableIntStateOf(CameraSelector.LENS_FACING_BACK) }

    val poses = listOf("STRAIGHT", "LEFT", "RIGHT")
    var currentPoseIndex by remember { mutableIntStateOf(0) }
    var isCaptureEnabled by remember { mutableStateOf(false) }
    val capturedImages = remember { mutableStateListOf<ByteArray>() }
    var pendingCompletionMessage by remember { mutableStateOf("") }

    LaunchedEffect(Unit) {
        urls = getLocalIpAddresses().map { "http://$it:${cameraServer.listeningPort}/register_payload" }
    }

    LaunchedEffect(registrationMode, currentPoseIndex, detectedFaces) {
        if (registrationMode && currentPoseIndex < poses.size) {
            val face = detectedFaces.firstOrNull()
            if (face != null) {
                val euler = face.eulerY
                val targetPose = poses[currentPoseIndex]
                isCaptureEnabled = when(targetPose) {
                    "STRAIGHT" -> abs(euler) < 12f
                    "LEFT" -> euler > 20f
                    "RIGHT" -> euler < -20f
                    else -> false
                }
            } else {
                isCaptureEnabled = false
            }
        }
    }

    if (showNameDialog) {
        AlertDialog(
            onDismissRequest = { showNameDialog = false },
            title = { Text("Register Face") },
            text = {
                Column {
                    Text("Enter the name of the person:")
                    Spacer(modifier = Modifier.height(8.dp))
                    OutlinedTextField(
                        value = registrationName,
                        onValueChange = { registrationName = it },
                        singleLine = true
                    )
                }
            },
            confirmButton = {
                Button(
                    onClick = {
                        if (registrationName.isNotBlank()) {
                            showNameDialog = false
                            registrationMode = true
                            currentPoseIndex = 0
                            capturedImages.clear()
                            pendingCompletionMessage = ""
                        }
                    }
                ) {
                    Text("Start Configuration")
                }
            },
            dismissButton = {
                TextButton(onClick = { showNameDialog = false }) {
                    Text("Cancel")
                }
            }
        )
    }

    IPCamTheme {
        Scaffold(modifier = Modifier.fillMaxSize()) { innerPadding ->
            Box(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(innerPadding)
            ) {
                // Camera Preview Layer
                CameraPreviewWithDetection(
                    modifier = Modifier.fillMaxSize(),
                    lensFacing = lensFacing,
                    onFrameAnalyzed = { bytes, faces ->
                        if (isServerRunning) {
                            cameraServer.currentFrame = bytes
                        }
                        detectedFaces = faces
                    }
                )

                // Face Bounding Box Layer
                Canvas(modifier = Modifier.fillMaxSize()) {
                    val canvasW = size.width
                    val canvasH = size.height

                    detectedFaces.forEach { face ->
                        val scaleX = canvasW / face.imageWidth
                        val scaleY = canvasH / face.imageHeight

                        val mirror = lensFacing == CameraSelector.LENS_FACING_FRONT

                        // calculate box
                        val leftOrig = face.boundingBox.left * scaleX
                        val top = face.boundingBox.top * scaleY
                        val width = face.boundingBox.width() * scaleX
                        val height = face.boundingBox.height() * scaleY

                        val left = if (mirror) canvasW - leftOrig - width else leftOrig

                        drawRect(
                            color = Color.Green,
                            topLeft = Offset(left, top),
                            size = Size(width, height),
                            style = Stroke(width = 8f)
                        )
                    }
                }

                // Interaction UI Layer
                if (!registrationMode) {
                    Column(
                        modifier = Modifier
                            .fillMaxWidth()
                            .background(Color.Black.copy(alpha = 0.5f))
                            .padding(16.dp)
                            .align(Alignment.TopCenter)
                    ) {
                        Text(
                            text = "Camera Server: ${if (isServerRunning) "RUNNING" else "STOPPED"}",
                            color = Color.White,
                            fontSize = 18.sp
                        )
                        Spacer(modifier = Modifier.height(8.dp))
                        if (isServerRunning) {
                            Text("Registration URL:", color = Color.White, fontSize = 14.sp)
                            urls.forEach {
                                Text(it, color = Color.Yellow, fontSize = 16.sp)
                            }
                        }
                    }
                } else {
                    Column(
                        modifier = Modifier
                            .fillMaxWidth()
                            .background(Color.Blue.copy(alpha = 0.7f))
                            .padding(16.dp)
                            .align(Alignment.TopCenter)
                    ) {
                        Text(text = "Registering: $registrationName", color = Color.White, fontSize = 20.sp)
                        Spacer(modifier = Modifier.height(16.dp))

                        if (pendingCompletionMessage.isNotEmpty()) {
                            Text(text = pendingCompletionMessage, color = Color.Green, fontSize = 20.sp)
                        } else if (currentPoseIndex < poses.size) {
                            val pose = poses[currentPoseIndex]
                            Text(text = "Action: Look $pose", color = Color.White, fontSize = 24.sp)

                            if (isCaptureEnabled) {
                                Text(text = "✓ PERFECT! Press Capture.", color = Color.Green, fontSize = 18.sp)
                            } else {
                                Text(text = "Please adjust head orientation...", color = Color.Red, fontSize = 18.sp)
                            }
                        }
                    }
                }

                // Professional Controls Layer
                Row(
                    modifier = Modifier
                        .align(Alignment.BottomCenter)
                        .padding(bottom = 48.dp)
                        .fillMaxWidth(),
                    horizontalArrangement = Arrangement.Center,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    if (!registrationMode) {
                        // Regular Controls
                        FilledIconButton(
                            onClick = {
                                lensFacing = if (lensFacing == CameraSelector.LENS_FACING_BACK)
                                    CameraSelector.LENS_FACING_FRONT
                                else
                                    CameraSelector.LENS_FACING_BACK
                            },
                            modifier = Modifier.size(56.dp),
                            colors = IconButtonDefaults.filledIconButtonColors(
                                containerColor = Color.DarkGray.copy(alpha = 0.7f)
                            )
                        ) {
                            Icon(Icons.Default.Cameraswitch, contentDescription = "Switch Camera", tint = Color.White)
                        }

                        Spacer(modifier = Modifier.width(32.dp))

                        FloatingActionButton(
                            onClick = {
                                if (isServerRunning) {
                                    cameraServer.stop()
                                    isServerRunning = false
                                } else {
                                    try {
                                        cameraServer.start()
                                        isServerRunning = true
                                        urls = getLocalIpAddresses().map { "http://$it:${cameraServer.listeningPort}/register_payload" }
                                    } catch (e: Exception) {
                                        e.printStackTrace()
                                    }
                                }
                            },
                            modifier = Modifier.size(80.dp),
                            shape = CircleShape,
                            containerColor = if (isServerRunning) Color.Red else Color.LightGray
                        ) {
                            Icon(
                                if (isServerRunning) Icons.Default.VideocamOff else Icons.Default.Videocam,
                                contentDescription = "Toggle Stream",
                                modifier = Modifier.size(40.dp),
                                tint = Color.White
                            )
                        }

                        Spacer(modifier = Modifier.width(32.dp))

                        if (isServerRunning) {
                            FilledIconButton(
                                onClick = { showNameDialog = true },
                                modifier = Modifier.size(56.dp),
                                colors = IconButtonDefaults.filledIconButtonColors(
                                    containerColor = Color.Blue.copy(alpha = 0.7f)
                                )
                            ) {
                                Icon(Icons.Default.PersonAdd, contentDescription = "Register Face", tint = Color.White)
                            }
                        } else {
                            Spacer(modifier = Modifier.size(56.dp))
                        }
                    } else {
                        // Registration Controls
                        if (currentPoseIndex < poses.size) {
                            FloatingActionButton(
                                onClick = {
                                    val frame = cameraServer.currentFrame
                                    if (frame != null) {
                                        capturedImages.add(frame)
                                        currentPoseIndex++

                                        if (currentPoseIndex >= poses.size) {
                                            cameraServer.registrationPayload = RegistrationPayload(registrationName, capturedImages.toList())
                                            pendingCompletionMessage = "SUCCESS! Pull data using Python script."
                                        }
                                    }
                                },
                                modifier = Modifier.size(80.dp),
                                containerColor = if (isCaptureEnabled) Color.Green else Color.DarkGray,
                                shape = CircleShape
                            ) {
                                Icon(
                                    Icons.Default.Camera,
                                    contentDescription = "Capture Frame",
                                    modifier = Modifier.size(40.dp),
                                    tint = Color.White
                                )
                            }
                            
                            Spacer(modifier = Modifier.width(32.dp))
                            
                            FilledIconButton(
                                onClick = { registrationMode = false }, // Cancel early
                                modifier = Modifier.size(56.dp),
                                colors = IconButtonDefaults.filledIconButtonColors(
                                    containerColor = Color.Red.copy(alpha = 0.7f)
                                )
                            ) {
                                Icon(Icons.Default.Close, contentDescription = "Cancel", tint = Color.White)
                            }
                        } else {
                            FloatingActionButton(
                                onClick = { registrationMode = false },
                                modifier = Modifier.size(80.dp),
                                containerColor = Color.Blue,
                                shape = CircleShape
                            ) {
                                Icon(
                                    Icons.Default.Close,
                                    contentDescription = "Done",
                                    modifier = Modifier.size(40.dp),
                                    tint = Color.White
                                )
                            }
                        }
                    }
                }
            }
        }
    }
}

@SuppressLint("UnsafeOptInUsageError")
@Composable
fun CameraPreviewWithDetection(
    modifier: Modifier = Modifier,
    lensFacing: Int,
    onFrameAnalyzed: (byteArray: ByteArray, faces: List<FaceTelemetry>) -> Unit
) {
    val context = LocalContext.current
    val lifecycleOwner = LocalLifecycleOwner.current
    val cameraProviderFuture = remember { ProcessCameraProvider.getInstance(context) }
    val backgroundExecutor = remember { Executors.newSingleThreadExecutor() }

    val detectorOptions = remember {
        FaceDetectorOptions.Builder()
            .setPerformanceMode(FaceDetectorOptions.PERFORMANCE_MODE_FAST)
            .setLandmarkMode(FaceDetectorOptions.LANDMARK_MODE_NONE)
            .setClassificationMode(FaceDetectorOptions.CLASSIFICATION_MODE_NONE)
            .build()
    }
    val detector = remember { FaceDetection.getClient(detectorOptions) }

    DisposableEffect(Unit) {
        onDispose {
            backgroundExecutor.shutdown()
            detector.close()
        }
    }

    AndroidView(
        factory = { ctx ->
            PreviewView(ctx).apply {
                implementationMode = PreviewView.ImplementationMode.COMPATIBLE
            }
        },
        update = { previewView ->
            cameraProviderFuture.addListener({
                val cameraProvider = cameraProviderFuture.get()

                val preview = androidx.camera.core.Preview.Builder()
                    .build()
                    .also {
                        it.setSurfaceProvider(previewView.surfaceProvider)
                    }

                val imageAnalysis = ImageAnalysis.Builder()
                    .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
                    .build()

                imageAnalysis.setAnalyzer(backgroundExecutor) { imageProxy: ImageProxy ->
                    val mediaImage = imageProxy.image
                    if (mediaImage != null) {
                        try {
                            val inputImage = InputImage.fromMediaImage(mediaImage, imageProxy.imageInfo.rotationDegrees)

                            val bitmap = imageProxy.toBitmap()
                            val stream = ByteArrayOutputStream()
                            bitmap.compress(Bitmap.CompressFormat.JPEG, 70, stream)
                            val bytes = stream.toByteArray()

                            detector.process(inputImage)
                                .addOnSuccessListener { faces ->
                                    val telemetries = faces.map {
                                        FaceTelemetry(it.boundingBox, it.headEulerAngleY, bitmap.width, bitmap.height)
                                    }
                                    onFrameAnalyzed(bytes, telemetries)
                                }
                                .addOnFailureListener {
                                    onFrameAnalyzed(bytes, emptyList())
                                }
                                .addOnCompleteListener {
                                    imageProxy.close()
                                }
                        } catch (e: Exception) {
                            imageProxy.close()
                        }
                    } else {
                        imageProxy.close()
                    }
                }

                val cameraSelector = CameraSelector.Builder()
                    .requireLensFacing(lensFacing)
                    .build()

                try {
                    cameraProvider.unbindAll()
                    cameraProvider.bindToLifecycle(
                        lifecycleOwner,
                        cameraSelector,
                        preview,
                        imageAnalysis
                    )
                } catch (e: Exception) {
                    Log.e("IPCam", "Use case binding failed", e)
                }
            }, ContextCompat.getMainExecutor(context))
        },
        modifier = modifier
    )
}

fun getLocalIpAddresses(): List<String> {
    val ips = mutableListOf<String>()
    try {
        val interfaces = NetworkInterface.getNetworkInterfaces()
        for (intf in interfaces) {
            for (enumIpAddr in intf.inetAddresses) {
                if (!enumIpAddr.isLoopbackAddress && enumIpAddr.address.size == 4) {
                    ips.add(enumIpAddr.hostAddress ?: "")
                }
            }
        }
    } catch (e: Exception) {
        Log.e("IPCam", "Failed to get network interfaces", e)
    }
    return ips
}