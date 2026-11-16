# TelecomInsight BW

**Telecommunications Service Quality and Customer Experience Analytics for Botswana**

TelecomInsight BW is a data analytics application designed to evaluate telecommunications service quality and customer experience in Botswana. It uses **Streamlit, Pandas, Plotly, and SQLAlchemy** to process telecommunications data, calculate performance indicators, identify trends, and generate analytical reports.

> **Note:** The application uses fictional demonstration data. The sample dataset does not represent actual telecommunications providers or their performance and must not be used to make claims about real providers.

## Project Structure

```text
TelecomInsight_BW/
│
├── app.py                          # Streamlit dashboard and user interface
│
├── telecominsight/
│   ├── config.py                   # Application configuration, paths, database URL,
│   │                               # data limits, source labels, and map coordinates
│   ├── cleaning.py                 # Data validation, cleaning, and cleaning reports (FR04)
│   ├── db.py                       # Database management using SQLAlchemy,
│   │                               # supporting SQLite and PostgreSQL (FR02)
│   ├── analysis.py                 # KPIs, trends, summaries, and analytical insights
│   │                               # (FR05, FR09)
│   └── report.py                   # PDF report generation (FR10)
│
├── data/
│   └── sample_telecom_data.csv      # Fictional demonstration dataset,
│                                   # loaded automatically on first run
│
├── tests/                          # Automated tests for cleaning, analysis,
│                                   # database operations, and application startup
│
├── docs/
│   └── TRACEABILITY.md              # Requirements-to-implementation traceability
│
├── .streamlit/
│   └── secrets.toml.example         # Example configuration for administrator access
│
├── requirements.txt                # Python dependencies
├── README.md                        # Project documentation
└── .gitignore                       # Files excluded from version control
```

## Installation and Setup

### Prerequisites

Ensure that you have the following installed:

- Python 3.10 or later
- pip (Python package manager)
- Visual Studio Code or another Python-compatible IDE

### 1. Clone the Repository

```powershell
git clone <repository-url>
cd TelecomInsight_BW
```

### 2. Create a Virtual Environment

On Windows (PowerShell):

```powershell
py -m venv .venv
```

Activate the virtual environment:

```powershell
.\.venv\Scripts\Activate.ps1
```

Alternatively, if you are using Command Prompt:

```cmd
.venv\Scripts\activate.bat
```

On macOS or Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install Dependencies

With the virtual environment activated, run:

```bash
python -m pip install -r requirements.txt
```

This installs the libraries required to run the application.

## Configuration

### Administrator Access

Uploading and removing datasets are restricted to administrators.

To enable administrator access, configure an administrator password using either of the following methods.

**Option 1: Streamlit Secrets**

1. Navigate to the `.streamlit/` directory.
2. Copy `secrets.toml.example` and rename the copy to `secrets.toml`.
3. Open `secrets.toml` and configure your password.

Example:

```toml
ADMIN_USER = admin1
ADMIN_PASSWORD = telecominsight

USER_NAME = btc_user
USER_PASSWORD = telecominsight
```

**Option 2: Environment Variable**

For Windows PowerShell:

```powershell
$env:ADMIN_PASSWORD = "your-password"
```

If no administrator password is configured, the dashboard remains accessible, but dataset uploads and removal are disabled.

> **Security:** Do not commit `secrets.toml` or expose administrator passwords in your source code or public repository.

## Database Configuration

TelecomInsight BW uses SQLAlchemy for database management.

### Default Database: SQLite

By default, the application automatically creates and uses a local SQLite database:

```text
telecominsight.db
```

No additional database configuration is required.

### PostgreSQL Configuration

The application also supports PostgreSQL databases, including hosted PostgreSQL services such as Neon.

To use PostgreSQL:

1. Create a PostgreSQL database.
2. Obtain your database connection URL.
3. Set the `DATABASE_URL` environment variable.

Example (Windows PowerShell):

```powershell
$env:DATABASE_URL = "postgresql+psycopg2://postgres:YOURPASSWORD@localhost:5432/telecominsight"
```

Replace the connection details with your actual database credentials.

The application automatically creates the required database tables when it runs for the first time.

## Running the Application

Ensure that your virtual environment is activated and that all dependencies have been installed.

From the project root directory, execute:

```bash
python -m streamlit run app.py
```

Streamlit will start the application and provide a local URL, typically:

```text
http://localhost:8501
```

Open this address in your browser to access the TelecomInsight BW dashboard.

## Running Tests

The project includes an automated test suite covering:

- Data cleaning and validation.
- Analytical calculations and KPI generation.
- Database operations.
- Application startup and basic functionality.

To execute the tests, run:

```bash
python -m pytest
```

Pytest will discover and execute the available tests in the `tests/` directory.

## CSV Dataset Format

TelecomInsight BW accepts CSV files containing telecommunications service-quality and customer-experience data.

### Required Columns

| Column | Description |
|---|---|
| `date` | Date of the recorded measurement or feedback |
| `provider` | Telecommunications service provider |
| `location` | City or geographical location |
| `issue_type` | Type of reported network issue |
| `download_mbps` | Download speed in Mbps |
| `upload_mbps` | Upload speed in Mbps |
| `latency_ms` | Network latency in milliseconds |
| `satisfaction` | Customer satisfaction rating |
| `complaint_reported` | Indicates whether a complaint was reported |

### Optional Columns

| Column | Description |
|---|---|
| `source` | Origin of the record |
| `latitude` | Geographic latitude |
| `longitude` | Geographic longitude |

The supported source categories include:

- `survey`
- `public_report`
- `network_measurement`
- `industry_data`
- `sample`

### Data Cleaning and Validation

When a CSV file is uploaded, the application performs data validation and cleaning before the dataset can be saved.

The cleaning process includes:

1. Validating required columns and data types.
2. Removing records containing invalid dates.
3. Filtering out impossible or invalid measurements.
4. Standardising text values and merging inconsistent text variations.
5. Identifying and removing duplicate records.
6. Generating a cleaning summary showing the changes made to the dataset.

The cleaning summary is displayed to the administrator before they decide whether to save the processed dataset.

> **Privacy:** Do not upload personally identifiable information or sensitive customer data.

## Known Limitations

The following limitations should be considered when interpreting the application's results:

1. **Administrator Authentication:** The application uses a single shared administrator password rather than individual user accounts. This provides basic access control but does not support role-based permissions or individual user tracking.

2. **Deployment Security:** When deploying the application publicly, HTTPS should be enabled to protect data transmitted between users and the application.

3. **Geographical Accuracy:** Map locations use approximate city-centre coordinates unless actual latitude and longitude values are supplied in the uploaded CSV file. These locations do not represent telecommunications tower positions, network coverage boundaries, or exact service availability.

4. **Provider Comparison:** Complaint rates are calculated using the number of complaints relative to the total number of records for each provider. Subscriber population figures are not available; therefore, the results do not represent complaint rates per subscriber.

5. **Demonstration Dataset:** The included sample dataset contains fictional records intended for testing and demonstration purposes only. Analytical results generated from this dataset should not be interpreted as actual telecommunications industry performance.

## Project Documentation

For additional information about the system's functional requirements and their implementation status, refer to:

```text
docs/TRACEABILITY.md
```

This document provides a mapping between the project's requirements and their corresponding implementation components.

---

**TelecomInsight BW**  
*Turning telecommunications data into meaningful service-quality insights.*
