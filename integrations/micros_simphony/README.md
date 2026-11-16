# Oracle MICROS Simphony POS adapter — SIMULATED

**Code:** `backend/app/integrations/micros_simphony.py`  
**Operations:** create_check, update_check_status, get_menu (menu sync), get_closed_checks (transaction sync), ping

## Sample payloads
- `sample_create_check_request.json`
- `sample_create_check_response.json`
- `sample_menu_item.json`

## Limitations of the simulation
Field names follow the style of Simphony's cloud APIs (locRef, checkRef, menuItemId) but this is not Oracle's published contract. A live integration needs an Oracle-issued API account, OAuth 2.0 client credentials and the customer's org/location hierarchy.

Full explanation: `documentation/04_INTEGRATION_ENGINEERING_HANDBOOK.md`.
