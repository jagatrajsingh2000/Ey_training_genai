import pandas as pd
import sqlite3

# Create in-memory database
conn = sqlite3.connect(':memory:')

# Server inventory data
servers_inventory = {
    "Host_ID": ["SRV-01", "SRV-02", "SRV-03"],
    "Role": ["Web Front", "API Gateway", "Database Replica"]
}

# Live interface data
live_interfaces = {
    "Interface_ID": ["eth0", "eth1"],
    "Mapped_Host": ["SRV-01", "SRV-02"],
    "IP_Address": ["10.0.0.4", "10.0.0.9"]
}

# Create DataFrames
df_srv = pd.DataFrame(servers_inventory)
df_inf = pd.DataFrame(live_interfaces)

# Load into SQL tables
df_srv.to_sql('Servers', conn, index=False, if_exists='replace')
df_inf.to_sql('Interfaces', conn, index=False, if_exists='replace')

# Q1: SRV-03 is excluded because INNER JOIN returns only matching records from both tables.

# Q2: Use LEFT JOIN to return all servers, even if they have no interface.

correct_query = """
SELECT
    s.Host_ID,
    s.Role,
    i.Interface_ID,
    i.IP_Address
FROM Servers s
LEFT JOIN Interfaces i
ON s.Host_ID = i.Mapped_Host;
"""

print("Output using LEFT JOIN:")
print(pd.read_sql_query(correct_query, conn))


# Q1: INNER JOIN returns only rows with matching values in both tables.
# SRV-03 has no matching record in Interfaces, so it is excluded.

# Q2: LEFT JOIN returns all records from Servers and matching records
# from Interfaces. Unmatched servers show NULL values.