# Zync - Chat Application Backend (FastAPI)

Welcome to the backend repository for Zync, a full-stack, real-time chat application. This backend is architected using Python (FastAPI) to provide high-performance RESTful APIs and WebSocket management for seamless user interaction, instant messaging, and dynamic UI updates.

**🚀 Frontend Repository:**
This is the backend component of Zync. The corresponding frontend (React) can be found here:
[Zync Frontend Repository](https://github.com/Aditya-kr-jha/chatapp-frontend)

## Overview

Engineered a full-stack, real-time chat application (”Zync”), architecting a high-performance Python (FastAPI) backend (RESTful APIs & WebSockets). This backend handles user authentication, channel management, real-time messaging via WebSockets, and secure file storage using AWS S3. It is designed to work in conjunction with a responsive React frontend.

## Table of Contents

- [Features](#features)
- [Technical Stack](#technical-stack)
- [Prerequisites](#prerequisites)
- [Setup Instructions](#setup-instructions)
  - [1. Clone the Repository](#1-clone-the-repository)
  - [2. Set Up Virtual Environment & Install Dependencies](#2-set-up-virtual-environment--install-dependencies)
  - [3. Configure Environment Variables](#3-configure-environment-variables)
  - [4. Database Setup](#4-database-setup)
  - [5. Run the Application](#5-run-the-application)
- [API Documentation](#api-documentation)
- [Key Workflows](#key-workflows)
- [Deployment](#deployment)
- [Contributing](#contributing)
- [License](#license)

## Features

-   **User Management:** Secure user registration (hashed passwords, duplicate checks), authentication (JWT & OAuth2), profile management (view, update, delete).
-   **Channel Management:** Creation of channels, user membership management.
-   **Message Management:**
    -   Sending and receiving text and file messages within channels.
    -   Retrieval of messages (paginated) for channels or by user.
    -   Message editing and deletion by authors or channel owners.
-   **Real-time Communication:** WebSocket integration for instant message broadcasting within channels.
-   **Secure File Storage:** Integration with AWS S3 for scalable storage of user-uploaded files, including secure uploads and pre-signed URL generation for access.
-   **Asynchronous Operations:** Leverages FastAPI's async capabilities and threadpools for non-blocking I/O.
-   **Data Validation:** Uses SQLModel (which integrates Pydantic) for robust data validation.
-   **Modularity:** Organized API with routers for users, channels, and messages.

## Technical Stack

-   **Framework:** FastAPI
-   **Database & ORM:** SQLModel (implies SQL-based DB like PostgreSQL, MySQL, SQLite)
-   **Authentication:** JWT (JSON Web Tokens), OAuth2 password flow
-   **Real-time:** WebSockets
-   **File Storage:** AWS S3, Boto3
-   **Asynchronous Programming:** `async/await`, `starlette.concurrency.run_in_threadpool`
-   **Configuration Management:** `python-dotenv` (assumed for `.env` loading)
-   **CORS:** FastAPI `CORSMiddleware`
-   **Logging:** Python `logging` module
-   **ASGI Server:** Uvicorn

## Prerequisites

-   Python 3.8+
-   Pip & Virtualenv
-   Git
-   A running PostgreSQL instance (or other SQL database compatible with your SQLModel setup).
-   An AWS Account with:
    -   An S3 bucket configured for file uploads.
    -   IAM user credentials with permissions for S3 operations.
-   Docker (Optional, for containerized deployment or development)

## Setup Instructions

### 1. Clone the Repository

```bash
# Assuming your backend repository is named zync-backend
git clone https://github.com/Aditya-kr-jha/zync-backend.git
cd zync-backend
```

### 2. Set Up Virtual Environment & Install Dependencies

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Configure Environment Variables

Create a `.env` file in the root of the project (or in `app/` if your config loader expects it there). Populate it with your specific configuration:

```env
# .env example

# Database Configuration
DATABASE_URL=postgresql://user:password@host:port/dbname

# JWT Settings
SECRET_KEY=your_very_strong_secret_key_for_jwt # Generate a strong random key
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

# AWS S3 Configuration
AWS_ACCESS_KEY_ID=your_aws_access_key_id
AWS_SECRET_ACCESS_KEY=your_aws_secret_access_key
AWS_DEFAULT_REGION=your_aws_s3_bucket_region # e.g., us-east-1
S3_BUCKET_NAME=your_s3_bucket_name

# CORS Origins (comma-separated if multiple, or adjust based on your CORS setup)
# Example: For local frontend development
FRONTEND_ORIGIN=http://localhost:5173 # Default Vite port

# Other application settings if any
# APP_ENV=development
```
**Note:** Ensure `SECRET_KEY` is strong and kept private.

### 4. Database Setup

The application uses SQLModel and has a function `create_db_and_tables()` which is typically called on startup to create database tables if they don't exist.
Ensure your `DATABASE_URL` in the `.env` file points to your active PostgreSQL (or other SQL) database.

### 5. Run the Application

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```
The backend API should now be running on `http://localhost:8000`.

## API Documentation

FastAPI automatically generates interactive API documentation. Once the server is running, you can access:
-   **Swagger UI:** `http://localhost:8000/docs`
-   **ReDoc:** `http://localhost:8000/redoc`

These interfaces allow you to explore and test all 30+ API endpoints.

## Key Workflows

-   **User Registration & Login:** Users sign up, then log in to receive a JWT.
-   **Joining a Channel:** Authenticated users can join existing channels.
-   **Sending a Message:**
    1.  User sends a message (text/file) to a channel endpoint with their JWT.
    2.  Backend validates, stores the message, (uploads file to S3 if applicable).
    3.  Message is broadcast via WebSocket to all connected clients in that channel.
-   **Real-time Updates:** Clients connected to a channel's WebSocket receive new messages instantly.

## Deployment

This backend is designed for scalable hosting and is deployed on **Render**.
-   Ensure environment variables are set in the Render service configuration.
-   The `uvicorn` command used for running locally can be adapted for the Render start command.

## Contributing

Contributions are welcome! Please follow these steps:
1.  Fork the repository.
2.  Create a new feature branch (`git checkout -b feature/your-amazing-feature`).
3.  Commit your changes (`git commit -m 'Add some amazing feature'`).
4.  Push to the branch (`git push origin feature/your-amazing-feature`).
5.  Open a Pull Request.

Please ensure your code adheres to any existing linting and formatting standards.

## License

This project is licensed under the MIT License. See the `LICENSE` file for more details.
