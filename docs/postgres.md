# PostgreSQL Integration in Memtext

Memtext supports PostgreSQL as an alternative database backend to SQLite, enabling enterprise-grade features while maintaining backward compatibility for individual developers.

## Enabling PostgreSQL

To use PostgreSQL instead of the default SQLite database, set the MEMTEXT_DATABASE_URL environment variable with your PostgreSQL connection string.

### Example

`ash
# Linux/macOS
export MEMTEXT_DATABASE_URL="postgresql://username:password@localhost/memtext_db"

# Windows (PowerShell)
 = "postgresql://username:password@localhost/memtext_db"
`

### Connection String Format

The connection string should follow the standard PostgreSQL URI format:
`
postgresql://[username[:password]@][host][:port][/dbname][?param1=value1&...]
`

## Dependencies

PostgreSQL support requires additional dependencies that are not installed by default to maintain a zero-dependency experience for SQLite users.

Install the PostgreSQL dependencies with:

`ash
pip install memtext[postgres]
`

Or if you have memtext installed in editable mode (for development):

`ash
pip install -e .[postgres]
`

This installs:
- syncpg: Asynchronous PostgreSQL client for Python
- pgvector: PostgreSQL extension for vector similarity search

## Verifying PostgreSQL Usage

After setting the environment variable and installing dependencies, you can verify that Memtext is using PostgreSQL with the db-status command:

`ash
memtext db-status
`

Example output when using PostgreSQL:
`
Database backend: PostgreSQL
Connection string: postgresql://****:****@localhost/memtext_db
PostgreSQL extensions: vector, pg_trgm, btree_gin (if available)
`

Note: The connection string masks credentials for security.

If PostgreSQL is not available or the connection fails, Memtext will fall back to SQLite and show an error in the status output.

## Advanced Features

When using PostgreSQL, Memtext unlocks several advanced features:

### 1. Hybrid Search
Combine traditional full-text search with vector similarity search for more relevant results.

### 2. Multi-Project Support
Shared context across multiple projects via the projects table.

### 3. Time-Series Tracking
Session logs are stored with time-series capabilities, suitable for extension with TimescaleDB.

### 4. Enhanced Indexing
Specialized indexes for full-text (GIN), trigram matching (GIN), and vector similarity (ivfflat).

## Development Notes

### Schema
The PostgreSQL schema includes:
- context_entries: Enhanced with UUIDs, full-text search vectors, and embedding columns
- projects: For tracking registered projects
- context_fts: Full-text search virtual table (FTS5 equivalent via pg_trgm)
- session_logs: For time-series session data
- And several indexes for performance

### Migrations
Memtext uses its own migration system. When switching to PostgreSQL, the initialization will create the enhanced schema automatically.

## Fallback Behavior

If PostgreSQL dependencies are not installed or the database connection fails, Memtext will automatically fall back to using SQLite. This ensures that individual developers can continue to work without any setup, while teams can enable PostgreSQL for advanced features when needed.

## Security Note

Always protect your PostgreSQL credentials. Consider using connection pooling or a .pgpass file for production environments. The memtext db-status command masks credentials in the output, but be cautious about logging or displaying the connection string elsewhere.

## Troubleshooting

### Common Issues

1. **Missing Dependencies**
   - Error: PostgreSQL dependencies not available
   - Solution: Install with pip install memtext[postgres]

2. **Connection Failed**
   - Error: [WinError 1225] The remote computer refused the network connection (or similar)
   - Solution: Verify that PostgreSQL is running and accessible at the specified host/port, and that the credentials are correct.

3. **Permission Denied**
   - Error: permission denied for database or similar
   - Solution: Ensure the PostgreSQL user has the necessary privileges to create tables and write to the specified database.

### Checking Status

Use memtext db-status to see which backend is active and diagnose connection issues.

## Back to SQLite

To switch back to SQLite, simply unset the MEMTEXT_DATABASE_URL environment variable:

`ash
# Linux/macOS
unset MEMTEXT_DATABASE_URL

# Windows (PowerShell)
Remove-Item env:MEMTEXT_DATABASE_URL
`

Then restart your Memtext commands.
