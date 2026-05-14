package com.routefood.app.core.supabase

import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.java_websocket.client.WebSocketClient
import org.java_websocket.handshake.ServerHandshake
import org.json.JSONArray
import org.json.JSONObject
import java.net.URI
import java.util.concurrent.atomic.AtomicInteger

class SupabaseRealtimeClient(
    private val scope: CoroutineScope,
    private val onStatus: (String) -> Unit = {},
    private val onDatabaseChange: (table: String) -> Unit
) {
    private var socket: WebSocketClient? = null
    private var heartbeatJob: Job? = null
    private var reconnectJob: Job? = null
    private val refs = AtomicInteger(1)
    private val joinedTopics = linkedMapOf<String, String>()

    fun connectDemoRun(demoRunId: String, tables: List<String>) {
        if (!SupabaseConfig.isConfigured()) {
            onStatus("Realtime disabled")
            return
        }
        disconnect()
        val endpoint = realtimeEndpoint()
        socket = object : WebSocketClient(endpoint) {
            override fun onOpen(handshakedata: ServerHandshake?) {
                onStatus("Realtime connected")
                tables.forEach { table -> joinPostgresChanges(table, demoRunId) }
                startHeartbeat()
            }

            override fun onMessage(message: String?) {
                if (message.isNullOrBlank()) return
                handleMessage(message)
            }

            override fun onClose(code: Int, reason: String?, remote: Boolean) {
                stopHeartbeat()
                onStatus("Realtime closed")
                scheduleReconnect(demoRunId, tables)
            }

            override fun onError(ex: Exception?) {
                onStatus("Realtime error: ${ex?.message ?: "unknown"}")
            }
        }.also { client ->
            client.addHeader("apikey", SupabaseConfig.publishableKey())
            client.addHeader("Authorization", "Bearer ${SupabaseConfig.publishableKey()}")
            client.connect()
        }
    }

    fun disconnect() {
        reconnectJob?.cancel()
        reconnectJob = null
        stopHeartbeat()
        socket?.close()
        socket = null
        joinedTopics.clear()
    }

    private fun realtimeEndpoint(): URI {
        val base = SupabaseConfig.url().trimEnd('/').replaceFirst("https://", "wss://").replaceFirst("http://", "ws://")
        val key = SupabaseConfig.publishableKey()
        return URI("$base/realtime/v1/websocket?apikey=$key&vsn=1.0.0")
    }

    private fun joinPostgresChanges(table: String, demoRunId: String) {
        val topic = "realtime:public:$table:demo_run_id=eq.$demoRunId"
        joinedTopics[topic] = table
        send(
            topic = topic,
            event = "phx_join",
            payload = JSONObject()
                .put("config", JSONObject()
                    .put("postgres_changes", JSONArray().put(JSONObject()
                        .put("event", "*")
                        .put("schema", "public")
                        .put("table", table)
                        .put("filter", "demo_run_id=eq.$demoRunId"))))
                .put("access_token", SupabaseConfig.publishableKey())
        )
    }

    private fun handleMessage(message: String) {
        val json = runCatching { JSONObject(message) }.getOrNull() ?: return
        val event = json.optString("event")
        if (event != "postgres_changes") return
        val topic = json.optString("topic")
        val table = joinedTopics[topic] ?: json.optJSONObject("payload")
            ?.optJSONObject("data")
            ?.optString("table")
            ?.takeIf { it.isNotBlank() }
            ?: return
        scope.launch(Dispatchers.Main) { onDatabaseChange(table) }
    }

    private fun send(topic: String, event: String, payload: JSONObject = JSONObject()) {
        val body = JSONObject()
            .put("topic", topic)
            .put("event", event)
            .put("payload", payload)
            .put("ref", refs.getAndIncrement().toString())
        socket?.send(body.toString())
    }

    private fun startHeartbeat() {
        stopHeartbeat()
        heartbeatJob = scope.launch(Dispatchers.IO) {
            while (true) {
                delay(25_000)
                send("phoenix", "heartbeat")
            }
        }
    }

    private fun stopHeartbeat() {
        heartbeatJob?.cancel()
        heartbeatJob = null
    }

    private fun scheduleReconnect(demoRunId: String, tables: List<String>) {
        if (reconnectJob?.isActive == true) return
        reconnectJob = scope.launch(Dispatchers.IO) {
            delay(2_000)
            withContext(Dispatchers.Main) { connectDemoRun(demoRunId, tables) }
        }
    }
}
