"""hotel KPI pipeline package.

Thin Python layer around the dbt/DuckDB transformation:
  * extract.py  -> EL: load raw PMS JSON into DuckDB (schema-on-read).
  * export.py   -> serve: copy the kpi_report mart to the contract CSV.
"""
