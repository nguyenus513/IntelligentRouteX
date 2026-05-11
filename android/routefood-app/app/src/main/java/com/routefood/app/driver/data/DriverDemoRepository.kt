package com.routefood.app.driver.data

import com.routefood.app.core.supabase.SupabaseConfig
import com.routefood.app.driver.model.DriverAssignmentDemo
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.io.BufferedReader
import java.io.OutputStreamWriter
import java.net.HttpURLConnection
import java.net.URLEncoder
import java.net.URL
import java.nio.charset.StandardCharsets

class DriverDemoRepository {
    private val baseUrl: String = SupabaseConfig.url().trimEnd('/')
    private val key: String = SupabaseConfig.publishableKey()

    suspend fun fetchActiveAssignment(
        demoRunId: String = DEFAULT_DEMO_RUN_ID,
        driverCode: String = DEFAULT_DRIVER_CODE
    ): Result<DriverAssignmentDemo?> = withContext(Dispatchers.IO) {
        runCatching {
            if (!SupabaseConfig.isConfigured()) return@runCatching DriverAssignmentDemo.sample()
            val query = linkedMapOf(
                "select" to "*",
                "demo_run_id" to "eq.$demoRunId",
                "driver_code" to "eq.$driverCode",
                "status" to "in.(assigned,accepted,in_progress)",
                "order" to "created_at.desc",
                "limit" to "1"
            )
            val array = JSONArray(get("assignments", query))
            if (array.length() == 0) null else DriverAssignmentDemo.fromJson(array.getJSONObject(0))
        }
    }

    suspend fun acceptAssignment(assignmentId: String): Result<Unit> = callDemoControl("accept_assignment", assignmentId)
    suspend fun rejectAssignment(assignmentId: String): Result<Unit> = callDemoControl("reject_assignment", assignmentId)
    suspend fun advanceAssignment(assignmentId: String): Result<Unit> = callDemoControl("advance_assignment", assignmentId)

    private suspend fun callDemoControl(action: String, assignmentId: String): Result<Unit> = withContext(Dispatchers.IO) {
        runCatching {
            if (!SupabaseConfig.isConfigured() || assignmentId == DriverAssignmentDemo.sample().id) return@runCatching
            val payload = JSONObject()
                .put("action", action)
                .put("assignmentId", assignmentId)
                .put("demoRunId", DEFAULT_DEMO_RUN_ID)
            val response = postFunction("demo-control", payload)
            val json = JSONObject(response)
            if (!json.optBoolean("ok", false)) {
                throw IllegalStateException(json.optString("error", "demo-control action failed"))
            }
        }
    }

    private fun get(table: String, query: Map<String, String>): String {
        val url = URL("$baseUrl/rest/v1/$table${queryString(query)}")
        val connection = (url.openConnection() as HttpURLConnection).apply {
            connectTimeout = 6000
            readTimeout = 6000
            requestMethod = "GET"
            setRequestProperty("apikey", key)
            setRequestProperty("Authorization", "Bearer $key")
            setRequestProperty("Accept", "application/json")
        }
        return readResponse(connection)
    }

    private fun postFunction(name: String, payload: JSONObject): String {
        val url = URL("$baseUrl/functions/v1/$name")
        val connection = (url.openConnection() as HttpURLConnection).apply {
            connectTimeout = 7000
            readTimeout = 7000
            requestMethod = "POST"
            doOutput = true
            setRequestProperty("apikey", key)
            setRequestProperty("Authorization", "Bearer $key")
            setRequestProperty("Content-Type", "application/json; charset=utf-8")
            setRequestProperty("Accept", "application/json")
        }
        OutputStreamWriter(connection.outputStream, StandardCharsets.UTF_8).use { it.write(payload.toString()) }
        return readResponse(connection)
    }

    private fun readResponse(connection: HttpURLConnection): String {
        val code = connection.responseCode
        val stream = if (code in 200..299) connection.inputStream else connection.errorStream
        val body = buildString {
            BufferedReader(stream.reader(StandardCharsets.UTF_8)).useLines { lines ->
                lines.forEach { append(it) }
            }
        }
        if (code !in 200..299) throw IllegalStateException("HTTP $code: $body")
        return body
    }

    private fun queryString(query: Map<String, String>): String {
        if (query.isEmpty()) return ""
        return query.entries.joinToString(prefix = "?", separator = "&") { (key, value) ->
            "${encode(key)}=${encode(value)}"
        }
    }

    private fun encode(value: String): String = URLEncoder.encode(value, StandardCharsets.UTF_8.name()).replace("+", "%20")

    companion object {
        const val DEFAULT_DEMO_RUN_ID = "demo-main"
        const val DEFAULT_DRIVER_CODE = "D1"
    }
}
