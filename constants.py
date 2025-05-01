from datetime import datetime, timedelta

CONFIG_FILENAME = "config.ini"
AUTH_URL = "https://api.rijbewijs.sbat.be/praktijk/api/user/authenticate"
AVAILABLE_URL = "https://api.rijbewijs.sbat.be/praktijk/api/exam/available"
USER_AGENT = "SBAT Exam Check GUI (github.com/fre-db/sbat-exam-check)"
CENTER_IDS = [
    (7, "Brakel"),
    (10, "Sint-Niklaas"),
    (1, "St-Denijs"),
    (9, "Erembodegem"),
    (8, "Eeklo"),
]
PAYLOAD_BASE = {
    "licenseType": "B",
    "examType": "E2",
    "startDate": f"{(datetime.now() + timedelta(hours=24)).strftime('%Y-%m-%d')}T00:00",
}

# An example response from the SBAT API
response_example = [
    {
        "id": 316276,
        "typesBlob": '["B"]',
        "examTypesBlob": '["E2"]',
        "examType": "E2",
        "from": "2024-08-30T10:15:00",
        "till": "2024-08-30T11:10:00",
        "dayScheduleId": 135,
        "examCenterId": 7,
        "drivingSchool": None,
        "examinee": None,
        "isPublic": True,
    },
    {
        "id": 316289,
        "typesBlob": '["B"]',
        "examTypesBlob": '["E2"]',
        "examType": "E2",
        "from": "2024-08-30T09:20:00",
        "till": "2024-08-30T10:15:00",
        "dayScheduleId": 131,
        "examCenterId": 7,
        "drivingSchool": None,
        "examinee": None,
        "isPublic": True,
    },
    {
        "id": 316341,
        "typesBlob": '["B"]',
        "examTypesBlob": '["E2"]',
        "examType": "E2",
        "from": "2024-08-30T11:10:00",
        "till": "2024-08-30T12:05:00",
        "dayScheduleId": 131,
        "examCenterId": 7,
        "drivingSchool": None,
        "examinee": None,
        "isPublic": True,
    },
    {
        "id": 340213,
        "typesBlob": '["B"]',
        "examTypesBlob": '["E2"]',
        "examType": "E2",
        "from": "2024-08-30T16:05:00",
        "till": "2024-08-30T17:00:00",
        "dayScheduleId": 131,
        "examCenterId": 7,
        "drivingSchool": None,
        "examinee": None,
        "isPublic": True,
    },
]
