# Coding Challenge: Hotel Performance KPIs

## Task Description

The product team is developing a performance dashboard for clients that displays key performance indicators (KPIs) including revenue, occupancy percentage, total net revenue and average daily rate (ADR) per day for hotels. Your responsibility is to build a reliable data pipeline that transforms raw PMS reservation events into trustworthy daily performance KPIs. Stakeholders require CSV exports from the transformed data, which should be exported and shared in the specified format.

## API Contract

You have a PMS that sends us data about hotel reservations. This PMS has the following structure for reservation data:

**GET <pms>/reservations:**

```json
{
  "data": [
    {
      "hotel_id": "<string>",
      "reservation_id": "<string>",
      "status": "<enum>", 
      "arrival_date": "<string>",
      "departure_date": "<string>",
      "created_at": "<string>",
      "updated_at": "<string>",
      "stay_dates": [
        {
          "start_date": "<string>",
          "end_date": "<string>",
          "room_type_id": "<string>",
          "room_type_name": "<string>",
          "room_revenue_gross_amount": "<string>",
          "room_revenue_net_amount": "<string>",
          "fnb_gross_amount": "<string>",
          "fnb_net_amount": "<string>"
        }
      ]
    }
  ]
}
```

### Field Explanations

**Top-Level Fields:**
- `data`: List of reservation objects. A reservation object represents only one room. **(Required)**

**Reservation Fields (each object in `data` array):**
- `hotel_id`: Unique identifier for the hotel **(Required)**
- `reservation_id`: Unique identifier for each reservation **(Required)**
- `status`: Status of the reservation. Possible values: `confirmed`, `cancelled`, `checked_in`, `checked_out` **(Required)**
- `arrival_date`: Check-in date (YYYY-MM-DD) **(Required)**
- `departure_date`: Check-out date (YYYY-MM-DD). Must be greater than `arrival_date` **(Required)**
- `created_at`: Timestamp when the reservation was created (UTC ISO-8601) **(Required)**
- `updated_at`: Timestamp when the reservation was last modified (UTC ISO-8601). When multiple entries exist for the same reservation on the same day, the reservation that counts is the last valid one **(Required)**
- `stay_dates`: List of stay date objects that provide information about each night of stay. Each stay date object contains a date range (`start_date` to `end_date`) representing one or more consecutive nights. When processing, each individual night within these ranges corresponds to a "night of stay" in the output. All dates must fall within the reservation period (between `arrival_date` and `departure_date`), and each date should appear only once across all stay date objects. **(Required)**

**Stay Date Object Fields:**
- `start_date`: Start date of stay range (YYYY-MM-DD) **(Required)**
- `end_date`: End date of stay range (YYYY-MM-DD) **(Required)**
- `room_type_id`: Room type ID **(Required)**
- `room_type_name`: Room type name **(Required)**
- `room_revenue_gross_amount`: Room gross revenue excluding other revenue and food & beverage. String value that can be converted to float (e.g., "1", "2.00", "123.45"). **(Required)**
- `room_revenue_net_amount`: Room net revenue excluding other revenue and food & beverage. String value that can be converted to float (e.g., "1", "2.00", "123.45"). **(Required)**
- `fnb_gross_amount`: Food & beverage gross revenue (total per room type and date). String value that can be converted to float (e.g., "1", "2.00", "123.45"). **(Optional)**
- `fnb_net_amount`: Food & beverage net revenue. String value that can be converted to float (e.g., "1", "2.00", "123.45"). **(Optional)**

**Note on date grouping:** In most cases, `start_date` and `end_date` will be equal, representing a single night of stay. However, when multiple consecutive stay dates share identical data (same `room_type_id`, `room_type_name`, and revenue amounts), the the PMS may group them into a single entry where `start_date` represents the first date and `end_date` represents the last date of the range. This grouping is an optimization feature to reduce data redundancy.

## Objective

Build a data pipeline that extracts reservation data from a JSON file and generates a CSV file for a single hotel with the following columns: `NIGHT_OF_STAY`, `OCCUPANCY_PERCENTAGE`, `TOTAL_NET_REVENUE` and `ADR`. 

Deliver a CSV file for hotel ID 1035 for May 2026.

**Note:** For simplification purposes, you can develop your solution assuming that all reservations for all hotels of a PMS are received in a single request. This simplification allows you to focus on the core data transformation and KPI calculation logic.

Submitting a correct implementation is necessary for advancing to the next interview stage. Please do not hesitate to ask questions if the instructions are unclear.

### Output Format

The contract between your team and the reporting team specifies the following CSV structure. The output must be sorted by NIGHT_OF_STAY (descending).

**Required CSV Columns (in order):**
- `NIGHT_OF_STAY`
- `OCCUPANCY_PERCENTAGE`
- `TOTAL_NET_REVENUE`
- `ADR`

### Field Explanations
- **NIGHT_OF_STAY**: The date for which the KPIs are calculated, formatted as `YYYY-MM-DD` (e.g., `2026-05-31`).

- **OCCUPANCY_PERCENTAGE**: Percentage of occupied rooms for each night of stay
  - Include all reservations with any status **except** `cancelled` when counting occupied rooms
  - Must be rounded to 2 decimal places
  - **Note:** It is possible to have overbooking, meaning the occupancy percentage can exceed 100%. For example, a hotel may have 4 rooms of a specific room type available, but 5 reservations for that room type on the same day. This is a common practice in the hospitality industry.
  
- **TOTAL_NET_REVENUE**: Total net revenue (room net revenue + food & beverage net revenue) for each night of stay.
  - Include all reservations with any status
  - Must be rounded to 2 decimal places

- **ADR** (Average Daily Rate): The average revenue earned per occupied room per day. Calculated by dividing the total net revenue by the number of occupied rooms for that night. The value should be rounded to the nearest integer (no decimal places). If the number of occupied rooms is zero, ADR is 0. 

Note that a row should be included for every `night_of_stay` in the requested date range, containing zeros in case of missing data.

### Output File Naming Convention

The output file should follow this naming pattern:
```
kpi_<hotel_id>_<yyyy>_<mm>_<dd>_to_<yyyy>_<mm>_<dd>.csv
```

Example: `kpi_1035_2026_05_01_to_2026_05_31.csv`

## Requirements

1. **Date Range Flexibility**: The pipeline must accept `hotel_id`, `from_date`, and `to_date` arguments to generate reports for any hotel and date range. The README should clearly explain how to run the pipeline with these arguments.

2. **Data Validation**: The PMS does not always send data that conforms to the API contract defined above. Any individual entry within a reservation that violates the API contract must be discarded.

3. **Output File**: The submission must include a CSV file containing the data for hotel ID 1035 for May 2026.
    - This file must be pre-generated and included directly in the submission.
    - Reviewers should not need to run your code to produce this output.
 
4. **Documentation**: Describe your decisions in a README file, including:
   - How to run the pipeline for different date ranges
   - Architecture and design decisions (see Architecture Expectations in the Objective section below)
   - How data flows through your pipeline
   - Any assumptions made

5. **Architecture & Design**: Describe the architecture of **what you actually implemented** for this challenge.
   - Your explanation should cover:
     - The main components of your pipeline
     - How data flows from input to output
     - Where and how intermediate data is stored or processed
   - An architecture diagram

- Please share your solution in a ZIP file via email

### What We Are NOT Expecting

The following items are **not required** and should not be prioritized:

- **Workflow orchestration tools (Airflow, Dagster, etc.)**: Orchestration is not required and will not be evaluated. Focus on the data transformation logic rather than scheduling or pipeline management infrastructure.

- **Production-ready configurations**: Basic setups for data processing tools are sufficient if you choose to use them. You don't need to implement production-grade error handling, monitoring, alerting, or deployment configurations.

- **Advanced infrastructure**: Cloud deployments, CI/CD pipelines, or complex infrastructure setup.

- **Unit and Integration tests**: While we appreciate well-tested code, tests are not required. Focus on demonstrating your core data transformation logic and pipeline architecture.

- **Performance optimization**: Basic performance considerations are fine, but you don't need to optimize for large-scale data processing or implement complex caching strategies.

**Focus on**: Getting the KPIs correct first; then a working pipeline that correctly transforms the data, demonstrates good code organization, and clearly explains your architectural decisions.

### Technologies
Use whatever you prefer: if you use dbt, a lightweight database like DuckDB is fine for local development. Otherwise, a Python script using pandas or polars is enough, and you can work with CSV files directly. Structure your code so that each function could later be mapped to a pipeline step if needed.


## Data

The following data files are provided.

- **reservation_data.json**: Contains reservation data from the the PMS. This JSON file includes real reservation information from multiple hotels, structured according to the schema described in the Data Source section above.

- **hotel_room_inventory.csv**: Contains the room inventory for each hotel, specifying the quantity of each room type available per hotel. This file defines which room types should be considered when calculating KPIs.
  
  **Important:** The reservation data from the PMS may include room types that:
  - No longer exist in the hotel's inventory
  - The hotel owner does not want to include in KPI calculations
  - You should **only** consider reservations for room types that appear in the `hotel_room_inventory.csv` file when calculating KPIs.

---

As a thank you for your time, we offer a €100 Uber voucher to everyone who completes and submits the challenge. Please do not hesitate to ask questions if the instructions are unclear.