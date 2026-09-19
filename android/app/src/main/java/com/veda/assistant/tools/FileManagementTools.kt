package com.veda.assistant.tools

import android.content.Context
import android.os.Environment
import org.json.JSONArray
import org.json.JSONObject
import java.io.File

class FileSearchTool(private val context: Context) : AndroidTool {
    override val name = "file_search"
    override val description = "Searches for files in device storage (Downloads, Documents, Pictures) matching a query."
    override val parametersSchema: JSONObject = JSONObject().apply {
        put("type", "object")
        put("properties", JSONObject().apply {
            put("query", JSONObject().put("type", "string").put("description", "Filename or keyword to search for"))
            put("folder", JSONObject().put("type", "string").put("description", "Target directory: 'downloads', 'documents', 'pictures', 'app_internal', or 'all'"))
        })
        put("required", org.json.JSONArray().put("query"))
    }

    override suspend fun execute(args: JSONObject): ToolResult {
        val query = args.optString("query", "").lowercase()
        val folderType = args.optString("folder", "downloads").lowercase()

        val searchDirs = mutableListOf<File>()
        when (folderType) {
            "downloads" -> searchDirs.add(Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS))
            "documents" -> searchDirs.add(Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOCUMENTS))
            "pictures" -> searchDirs.add(Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_PICTURES))
            "app_internal" -> searchDirs.add(context.filesDir)
            else -> {
                searchDirs.add(Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS))
                searchDirs.add(Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOCUMENTS))
                searchDirs.add(context.filesDir)
            }
        }

        val matches = mutableListOf<String>()
        for (dir in searchDirs) {
            if (dir.exists() && dir.isDirectory) {
                dir.walkTopDown().maxDepth(3).forEach { file ->
                    if (file.name.lowercase().contains(query)) {
                        matches.add("${file.name} (${file.length() / 1024} KB) - ${file.parent}")
                        if (matches.size >= 10) return@forEach
                    }
                }
            }
        }

        return if (matches.isNotEmpty()) {
            ToolResult(
                success = true,
                resultText = "Found ${matches.size} files matching '$query':\n" + matches.joinToString("\n• ", prefix = "• ")
            )
        } else {
            ToolResult(
                success = true,
                resultText = "No files found matching '$query' in $folderType folder."
            )
        }
    }
}

class FileManageTool(private val context: Context) : AndroidTool {
    override val name = "file_manage"
    override val description = "Reads, creates, or deletes text files in app storage or shared downloads."
    override val parametersSchema: JSONObject = JSONObject().apply {
        put("type", "object")
        put("properties", JSONObject().apply {
            put("action", JSONObject().put("type", "string").put("description", "'read', 'write', 'delete'"))
            put("filename", JSONObject().put("type", "string").put("description", "Name of the file (e.g. 'notes.txt')"))
            put("content", JSONObject().put("type", "string").put("description", "Content to write when action is 'write'"))
        })
        put("required", org.json.JSONArray().put("action").put("filename"))
    }

    override suspend fun execute(args: JSONObject): ToolResult {
        val action = args.optString("action", "read").lowercase()
        val filename = args.optString("filename", "note.txt")
        val content = args.optString("content", "")

        val targetFile = File(context.filesDir, filename)

        return when (action) {
            "write" -> {
                targetFile.writeText(content)
                ToolResult(true, "Successfully wrote to ${targetFile.name} (${targetFile.length()} bytes)")
            }
            "delete" -> {
                if (targetFile.exists()) {
                    targetFile.delete()
                    ToolResult(true, "Deleted file ${targetFile.name}")
                } else {
                    ToolResult(false, "File does not exist: $filename")
                }
            }
            else -> {
                if (targetFile.exists()) {
                    val text = targetFile.readText().take(2000)
                    ToolResult(true, "Content of ${targetFile.name}:\n$text")
                } else {
                    ToolResult(false, "File $filename not found in storage.")
                }
            }
        }
    }
}
