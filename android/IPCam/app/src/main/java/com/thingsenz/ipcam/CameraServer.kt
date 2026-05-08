package com.thingsenz.ipcam

import fi.iki.elonen.NanoHTTPD
import java.io.InputStream
import kotlin.math.min
import android.util.Base64
import org.json.JSONArray
import org.json.JSONObject

data class RegistrationPayload(
    val name: String,
    val images: List<ByteArray>
)

class CameraServer(port: Int) : NanoHTTPD(port) {

    @Volatile
    var currentFrame: ByteArray? = null

    @Volatile
    var registrationPayload: RegistrationPayload? = null

    override fun serve(session: IHTTPSession): Response {
        if (session.uri == "/register_payload") {
            val payload = registrationPayload
            if (payload == null) {
                return newFixedLengthResponse(Response.Status.NOT_FOUND, "application/json", "{\"error\": \"No payload pending\"}")
            }

            // Construct JSON
            val json = JSONObject()
            json.put("name", payload.name)

            val imagesArray = JSONArray()
            payload.images.forEach { bytes ->
                val b64 = Base64.encodeToString(bytes, Base64.NO_WRAP)
                imagesArray.put(b64)
            }
            json.put("images", imagesArray)

            // Clear payload after serving so it's not reused
            registrationPayload = null

            val res = newFixedLengthResponse(Response.Status.OK, "application/json", json.toString())
            res.addHeader("Cache-Control", "no-cache, private")
            return res
        }

        if (session.uri != "/video") {
            return newFixedLengthResponse(Response.Status.NOT_FOUND, MIME_PLAINTEXT, "Not Found. Try /video or /register_payload")
        }

        val res = newChunkedResponse(
            Response.Status.OK,
            "multipart/x-mixed-replace; boundary=--BoundaryString",
            MjpegInputStream(this)
        )
        // Disable caching
        res.addHeader("Cache-Control", "no-cache, private")
        res.addHeader("Pragma", "no-cache")
        res.addHeader("Expires", "0")
        return res
    }

    class MjpegInputStream(private val server: CameraServer) : InputStream() {
        private var currentBuffer = ByteArray(0)
        private var bufferPos = 0

        override fun read(): Int {
            if (bufferPos >= currentBuffer.size) {
                loadNextFrame()
            }
            if (currentBuffer.isEmpty()) return -1
            return currentBuffer[bufferPos++].toInt() and 0xFF
        }

        override fun read(b: ByteArray, off: Int, len: Int): Int {
            if (bufferPos >= currentBuffer.size) {
                loadNextFrame()
            }
            if (currentBuffer.isEmpty()) return -1

            val toCopy = min(len, currentBuffer.size - bufferPos)
            System.arraycopy(currentBuffer, bufferPos, b, off, toCopy)
            bufferPos += toCopy
            return toCopy
        }

        private fun loadNextFrame() {
            var frame = server.currentFrame
            // Wait for a frame if null
            while (frame == null) {
                try { Thread.sleep(50) } catch (e: InterruptedException) { return }
                frame = server.currentFrame
            }

            val header = "--BoundaryString\r\n" +
                    "Content-type: image/jpeg\r\n" +
                    "Content-Length: ${frame.size}\r\n\r\n"
            val headerBytes = header.toByteArray()
            val footerBytes = "\r\n\r\n".toByteArray()

            currentBuffer = ByteArray(headerBytes.size + frame.size + footerBytes.size)
            System.arraycopy(headerBytes, 0, currentBuffer, 0, headerBytes.size)
            System.arraycopy(frame, 0, currentBuffer, headerBytes.size, frame.size)
            System.arraycopy(footerBytes, 0, currentBuffer, headerBytes.size + frame.size, footerBytes.size)

            bufferPos = 0

            // Cap the streaming to roughly ~30 fps max and prevent CPU spinning
            try {
                Thread.sleep(30)
            } catch (e: InterruptedException) {
                // Return if interrupted
                currentBuffer = ByteArray(0)
            }
        }
    }
}
