from posthog.settings.utils import get_from_env

HUBSPOT_APP_CLIENT_ID = get_from_env("HUBSPOT_APP_CLIENT_ID", "")
HUBSPOT_APP_CLIENT_SECRET = get_from_env("HUBSPOT_APP_CLIENT_SECRET", "")

SNAPCHAT_APP_CLIENT_ID = get_from_env("SNAPCHAT_APP_CLIENT_ID", "")
SNAPCHAT_APP_CLIENT_SECRET = get_from_env("SNAPCHAT_APP_CLIENT_SECRET", "")

INTERCOM_APP_CLIENT_ID = get_from_env("INTERCOM_APP_CLIENT_ID", "")
INTERCOM_APP_CLIENT_SECRET = get_from_env("INTERCOM_APP_CLIENT_SECRET", "")

SALESFORCE_CONSUMER_KEY = get_from_env("SALESFORCE_CONSUMER_KEY", "")
SALESFORCE_CONSUMER_SECRET = get_from_env("SALESFORCE_CONSUMER_SECRET", "")

LINKEDIN_APP_CLIENT_ID = get_from_env("LINKEDIN_APP_CLIENT_ID", "")
LINKEDIN_APP_CLIENT_SECRET = get_from_env("LINKEDIN_APP_CLIENT_SECRET", "")

GOOGLE_ADS_APP_CLIENT_ID = get_from_env("GOOGLE_ADS_APP_CLIENT_ID", "")
GOOGLE_ADS_APP_CLIENT_SECRET = get_from_env("GOOGLE_ADS_APP_CLIENT_SECRET", "")
GOOGLE_ADS_DEVELOPER_TOKEN = get_from_env("GOOGLE_ADS_DEVELOPER_TOKEN", "")

LINEAR_APP_CLIENT_ID = get_from_env("LINEAR_APP_CLIENT_ID", "")
LINEAR_APP_CLIENT_SECRET = get_from_env("LINEAR_APP_CLIENT_SECRET", "")

GITHUB_APP_CLIENT_ID = get_from_env("GITHUB_APP_CLIENT_ID", "")
GITHUB_APP_PRIVATE_KEY = get_from_env("GITHUB_APP_PRIVATE_KEY", "")

ZENDESK_ADMIN_EMAIL = get_from_env("ZENDESK_ADMIN_EMAIL", "")
ZENDESK_API_TOKEN = get_from_env("ZENDESK_API_TOKEN", "")
ZENDESK_SUBDOMAIN = get_from_env("ZENDESK_SUBDOMAIN", "posthoghelp")

META_ADS_APP_CLIENT_ID = get_from_env("META_ADS_APP_CLIENT_ID", "")
META_ADS_APP_CLIENT_SECRET = get_from_env("META_ADS_APP_CLIENT_SECRET", "")
