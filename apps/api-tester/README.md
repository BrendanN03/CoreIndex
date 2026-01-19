# API Tester

Simple HTML frontend to test the Compute Market Exchange API.

## Usage

1. Start your API server:
   ```bash
   cd apps/api
   source venv/bin/activate
   uvicorn app.main:app --reload
   ```

2. Open `index.html` in your web browser (double-click the file, or use a simple HTTP server)

3. The default API URL is `http://localhost:8000` - you can change it at the top if needed

4. Test all endpoints:
   - **Buyer endpoints**: Create jobs, check feasibility, get job status
   - **Provider endpoints**: Create nominations, attest readiness, submit results

## Features

- ✅ Test all API endpoints
- ✅ Visual form inputs for all parameters
- ✅ See responses in formatted JSON
- ✅ Add/remove multiple packages when creating jobs
- ✅ Change API base URL
- ✅ Connection test button

## Note

For testing lot endpoints (`/lots/{id}/prepare_ready` and `/lots/{id}/result`), you'll need to create a lot first. Currently, lots must be created programmatically (not via API endpoint).
