"""Configuration management for Grow API pipeline."""
import os
from dataclasses import dataclass
from dotenv import load_dotenv


@dataclass
class Config:
    """Pipeline configuration loaded from environment variables."""

    grow_client_id: str
    grow_client_secret: str
    bigquery_project: str
    bigquery_dataset: str
    google_application_credentials: str = None
    grow_bearer_token: str = None

    @classmethod
    def load(cls) -> "Config":
        """Load configuration from .env file."""
        load_dotenv()

        # Required environment variables
        required_vars = {
            "GROW_CLIENT_ID": "grow_client_id",
            "GROW_CLIENT_SECRET": "grow_client_secret",
            "BIGQUERY_PROJECT": "bigquery_project",
            "BIGQUERY_DATASET": "bigquery_dataset",
        }

        # Optional environment variables
        optional_vars = {
            "GOOGLE_APPLICATION_CREDENTIALS": "google_application_credentials",
            "GROW_BEARER_TOKEN": "grow_bearer_token",
        }

        # Check all required variables exist
        missing_vars = []
        config_values = {}

        for env_var, field_name in required_vars.items():
            value = os.getenv(env_var)
            if not value:
                missing_vars.append(env_var)
            else:
                config_values[field_name] = value

        if missing_vars:
            raise ValueError(
                f"Missing required environment variables: {', '.join(missing_vars)}\n"
                f"Please ensure these are set in your .env file."
            )

        # Add optional variables
        for env_var, field_name in optional_vars.items():
            value = os.getenv(env_var)
            if value:
                config_values[field_name] = value

        return cls(**config_values)
