# Generated by Django 4.2.22 on 2025-06-26 15:18

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("posthog", "0778_dashboard_last_refresh"),
    ]

    operations = [
        migrations.AlterField(
            model_name="integration",
            name="kind",
            field=models.CharField(
                choices=[
                    ("slack", "Slack"),
                    ("salesforce", "Salesforce"),
                    ("hubspot", "Hubspot"),
                    ("google-pubsub", "Google Pubsub"),
                    ("google-cloud-storage", "Google Cloud Storage"),
                    ("google-ads", "Google Ads"),
                    ("snapchat", "Snapchat"),
                    ("linkedin-ads", "Linkedin Ads"),
                    ("intercom", "Intercom"),
                    ("email", "Email"),
                    ("linear", "Linear"),
                    ("github", "Github"),
                ],
                max_length=20,
            ),
        ),
    ]
