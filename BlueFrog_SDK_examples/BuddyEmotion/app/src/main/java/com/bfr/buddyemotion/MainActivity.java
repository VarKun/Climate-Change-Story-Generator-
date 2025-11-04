package com.bfr.buddyemotion;

import android.os.Bundle;
import android.util.Log;
import android.widget.TextView;
import android.widget.Toast;

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

    private static final String TAG = "BuddyEmotion";
    private static final String SOCKET_HOST = resolveSocketHost();
    private static final int SOCKET_PORT = resolveSocketPort();

    private final ExecutorService writerExecutor = Executors.newSingleThreadExecutor();
    private final ExecutorService listenerExecutor = Executors.newSingleThreadExecutor();
    private Future<?> listenerFuture;
    private Socket socket;
    private PrintWriter writer;
    private BufferedReader reader;
    private TextView statusText;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        statusText = findViewById(R.id.statusText);
        writerExecutor.execute(this::openSocketConnection);
    }

    @Override
    public void onSDKReady() {
        BuddySDK.UI.setViewAsFace(findViewById(R.id.view_face));
    }

    private void openSocketConnection() {
        closeSocket();
        try {
            socket = new Socket(SOCKET_HOST, SOCKET_PORT);
            writer = new PrintWriter(socket.getOutputStream(), true);
            reader = new BufferedReader(new InputStreamReader(socket.getInputStream()));
            writer.println("ROLE:android");
            runOnUiThread(() -> {
                statusText.setText("Connected to server");
                Toast.makeText(this, "Python server connected", Toast.LENGTH_SHORT).show();
            });
            startListeningForServerMessages();
        } catch (IOException e) {
            Log.e(TAG, "Failed to connect to Python server", e);
            runOnUiThread(() -> {
                statusText.setText("Connection failed");
                Toast.makeText(this, "Socket connect failed", Toast.LENGTH_SHORT).show();
            });
        }
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

        if ("SAY".equals(command)) {
            handleSayCommand(payload);
        } else {
            Toast.makeText(this, "Command received", Toast.LENGTH_SHORT).show();
        }
    }

    private void handleSayCommand(String payload) {
        if (payload == null) {
            return;
        }
        String text = payload.replace("\\n", "\n").trim();
        if (text.isEmpty()) {
            return;
        }

        String lower = text.toLowerCase(Locale.ROOT);
        FacialExpression expression;
        String speech;

        if (lower.contains("positive")) {
            expression = FacialExpression.HAPPY;
            speech = text;

        } else if (lower.contains("negative")) {
            expression = FacialExpression.SAD;
            speech = text;

        } else if (lower.contains("undecided")) {
            expression = FacialExpression.NEUTRAL;
            speech = "I'm undecided too. Let's think about it.";
        } else {
            expression = FacialExpression.NEUTRAL;
            speech = text;
        }

        BuddySDK.UI.setFacialExpression(expression);
        BuddySDK.Speech.startSpeaking(speech);
        statusText.setText(speech);
        Toast.makeText(this, "Responding to mood", Toast.LENGTH_SHORT).show();
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
}
