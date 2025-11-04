package com.bfr.helloworld;

import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.os.Bundle;
import android.os.RemoteException;
import android.util.Base64;
import android.util.Log;
import android.view.View;
import android.view.WindowManager;
import android.widget.ImageView;
import android.widget.Toast;

import androidx.core.view.WindowCompat;

import com.bfr.buddy.speech.shared.ITTSCallback;
import com.bfr.buddy.ui.shared.FacialExpression;
import com.bfr.buddysdk.BuddyActivity;
import com.bfr.buddysdk.BuddySDK;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.PrintWriter;
import java.net.Socket;
import java.util.Locale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class MainActivity extends BuddyActivity {

    private static final String TAG = "HelloWorldSocket";
    private static final String SOCKET_HOST = resolveSocketHost();
    private static final int SOCKET_PORT = resolveSocketPort();

    private final ExecutorService writerExecutor = Executors.newSingleThreadExecutor();
    private final ExecutorService listenerExecutor = Executors.newSingleThreadExecutor();
    private Future<?> listenerFuture;
    private Socket socket;
    private PrintWriter writer;
    private BufferedReader reader;
    private ImageView storyImageView;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        WindowCompat.setDecorFitsSystemWindows(getWindow(), false);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS);
        setContentView(R.layout.activity_main);

        storyImageView = findViewById(R.id.storyImageView);
        storyImageView.setScaleType(ImageView.ScaleType.CENTER_CROP);
        writerExecutor.execute(this::openSocketConnection);
    }

    @Override
    public void onSDKReady() {
        BuddySDK.UI.setViewAsFace(findViewById(R.id.view_face));

        findViewById(R.id.buttonHello).setOnClickListener(view -> {
            BuddySDK.Speech.startSpeaking("Hello World, I am Buddy from Southampton");
            sendMessageToServer("Hello from Android!");
        });
    }

    private void openSocketConnection() {
        closeSocket();
        try {
            socket = new Socket(SOCKET_HOST, SOCKET_PORT);
            writer = new PrintWriter(socket.getOutputStream(), true);
            reader = new BufferedReader(new InputStreamReader(socket.getInputStream()));
            writer.println("ROLE:android");
            runOnUiThread(() -> Toast.makeText(this, "Python server connected", Toast.LENGTH_SHORT).show());
            startListeningForServerMessages();
        } catch (IOException e) {
            Log.e(TAG, "Failed to connect to Python server", e);
            runOnUiThread(() -> Toast.makeText(this, "Socket connect failed", Toast.LENGTH_SHORT).show());
        }
    }

    private void sendMessageToServer(String message) {
        writerExecutor.execute(() -> {
            if (!ensureSocket()) {
                runOnUiThread(() -> Toast.makeText(this, "Socket unavailable", Toast.LENGTH_SHORT).show());
                return;
            }
            writer.println(message);
        });
    }

    private boolean ensureSocket() {
        if (socket != null && socket.isConnected() && !socket.isClosed() && writer != null && reader != null) {
            return true;
        }
        openSocketConnection();
        return socket != null && socket.isConnected() && !socket.isClosed() && writer != null && reader != null;
    }

    private static String resolveSocketHost() {
        String envHost = System.getenv("BUDDY_SOCKET_HOST");
        if (envHost != null && !envHost.trim().isEmpty()) {
            return envHost.trim();
        }
        String buildHost = BuildConfig.BUDDY_SOCKET_HOST;
        if (buildHost != null && !buildHost.trim().isEmpty()) {
            return buildHost.trim();
        }
        return "127.0.0.1";
    }

    private static int resolveSocketPort() {
        String envPort = System.getenv("BUDDY_SOCKET_PORT");
        if (envPort != null && envPort.matches("\\d{2,5}")) {
            return Integer.parseInt(envPort);
        }
        return BuildConfig.BUDDY_SOCKET_PORT;
    }

    private void startListeningForServerMessages() {
        if (reader == null) {
            return;
        }
        if (listenerFuture != null && !listenerFuture.isDone()) {
            listenerFuture.cancel(true);
        }
        listenerFuture = listenerExecutor.submit(this::listenForServerMessages);
    }

    private void listenForServerMessages() {
        try {
            String line;
            while (!Thread.currentThread().isInterrupted() && reader != null && (line = reader.readLine()) != null) {
                final String message = line;
                runOnUiThread(() -> handleServerMessage(message));
            }
        } catch (IOException e) {
            if (!Thread.currentThread().isInterrupted()) {
                Log.e(TAG, "Socket listen failed", e);
                runOnUiThread(() -> Toast.makeText(this, "Socket listen error", Toast.LENGTH_SHORT).show());
            }
        }
    }

    private void handleServerMessage(String message) {
        if (message == null || message.isEmpty()) {
            return;
        }

        final int delimiter = message.indexOf(':');
        final String command;
        final String payload;
        if (delimiter > 0) {
            command = message.substring(0, delimiter);
            payload = message.substring(delimiter + 1);
        } else {
            command = message;
            payload = "";
        }

        switch (command) {
            case "SAY":
                handleSayCommand(payload);
                break;
            case "SAY_STORY":
                handleStoryCommand(payload);
                break;
            case "IMAGE_BASE64":
                handleImageBase64Command(payload);
                break;
            default:
                Toast.makeText(this, "Command received", Toast.LENGTH_SHORT).show();
                break;
        }
    }

    private void handleImageBase64Command(String payload) {
        if (payload == null || payload.isEmpty()) {
            return;
        }
        try {
            byte[] decoded = Base64.decode(payload.trim(), Base64.DEFAULT);
            Bitmap bitmap = BitmapFactory.decodeByteArray(decoded, 0, decoded.length);
            if (bitmap != null) {
                storyImageView.setImageBitmap(bitmap);
                storyImageView.setVisibility(View.VISIBLE);
                storyImageView.setContentDescription("Story illustration");
            }
        } catch (IllegalArgumentException e) {
            Log.e(TAG, "Failed to decode image payload", e);
            Toast.makeText(this, "Invalid image data", Toast.LENGTH_SHORT).show();
        }
    }

    private void handleSayCommand(String payload) {
        if (payload == null) {
            return;
        }
        String toSpeak = payload.replace("\\n", "\n").trim();
        if (toSpeak.isEmpty()) {
            return;
        }

        // skip generic or meta descriptions
        String lower = toSpeak.toLowerCase(Locale.ROOT);
        if (lower.startsWith("here is a") || lower.startsWith("story:")) {
            return;
        }

        FacialExpression expression = null;
        if (lower.contains("positive")) {
            expression = FacialExpression.HAPPY;
        } else if (lower.contains("negative")) {
            expression = FacialExpression.SAD;
        }

        if (lower.contains("undecided")) {
            expression = FacialExpression.NEUTRAL;
        }

        if (expression != null) {
            BuddySDK.UI.setFacialExpression(expression);
        }

        if (lower.contains("undecided")) {
            BuddySDK.Speech.startSpeaking("I'm not sure what you mean");
        } else {
            BuddySDK.Speech.startSpeaking(toSpeak);
        }

        Toast.makeText(this, "Narrating story", Toast.LENGTH_SHORT).show();
    }

    private void handleStoryCommand(String payload) {
        if (payload == null) {
            return;
        }
        String story = payload.replace("\\n", "\n").trim();
        if (story.isEmpty()) {
            return;
        }

        BuddySDK.UI.setFacialExpression(FacialExpression.NEUTRAL);
        speakWithStoryReset(story);
        Toast.makeText(this, "Telling story", Toast.LENGTH_SHORT).show();
    }

    private void speakWithStoryReset(String text) {
        BuddySDK.Speech.startSpeaking(text, new ITTSCallback.Stub() {
            @Override
            public void onSuccess(String s) throws RemoteException {
                runOnUiThread(() -> {
                    storyImageView.setVisibility(View.GONE);
                    BuddySDK.UI.setFacialExpression(FacialExpression.NEUTRAL);
                });
            }

            @Override
            public void onPause() throws RemoteException {
            }

            @Override
            public void onResume() throws RemoteException {
            }

            @Override
            public void onError(String s) throws RemoteException {
                runOnUiThread(() -> {
                    storyImageView.setVisibility(View.GONE);
                    BuddySDK.UI.setFacialExpression(FacialExpression.NEUTRAL);
                });
            }
        });
    }

    private synchronized void closeSocket() {
        if (listenerFuture != null) {
            listenerFuture.cancel(true);
            listenerFuture = null;
        }
        try {
            if (reader != null) {
                reader.close();
            }
        } catch (IOException ignored) {
        }
        if (writer != null) {
            writer.close();
        }
        try {
            if (socket != null) {
                socket.close();
            }
        } catch (IOException ignored) {
        }
        reader = null;
        writer = null;
        socket = null;
    }

    @Override
    protected void onDestroy() {
        super.onDestroy();
        closeSocket();
        writerExecutor.shutdownNow();
        listenerExecutor.shutdownNow();
        try {
            writerExecutor.awaitTermination(1, TimeUnit.SECONDS);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
        try {
            listenerExecutor.awaitTermination(1, TimeUnit.SECONDS);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }
}
