import json
from unittest import mock
from uuid import UUID

from freezegun.api import freeze_time
from orjson import orjson
from flaky import flaky
from rest_framework import status

from posthog.helpers.dashboard_templates import create_group_type_mapping_detail_dashboard
from posthog.hogql.parser import parse_select
from posthog.hogql import ast
from posthog.hogql.query import execute_hogql_query
from posthog.models import GroupTypeMapping, Person
from posthog.models.group.util import create_group
from posthog.models.organization import Organization
from posthog.models.sharing_configuration import SharingConfiguration
from posthog.models.team.team import Team
from posthog.test.base import (
    APIBaseTest,
    ClickhouseTestMixin,
    _create_event,
    snapshot_clickhouse_queries,
)
from unittest.mock import patch


class ClickhouseTestGroupsApi(ClickhouseTestMixin, APIBaseTest):
    maxDiff = None

    @freeze_time("2021-05-02")
    def test_groups_list(self):
        with freeze_time("2021-05-01"):
            create_group(
                team_id=self.team.pk,
                group_type_index=0,
                group_key="org:5",
                properties={"industry": "finance", "name": "Mr. Krabs"},
            )
        with freeze_time("2021-05-02"):
            create_group(
                team_id=self.team.pk,
                group_type_index=0,
                group_key="org:6",
                properties={"industry": "technology"},
            )
        create_group(
            team_id=self.team.pk,
            group_type_index=1,
            group_key="company:1",
            properties={"name": "Plankton"},
        )

        response_data = self.client.get(f"/api/projects/{self.team.id}/groups?group_type_index=0").json()
        self.assertEqual(
            response_data,
            {
                "next": None,
                "previous": None,
                "results": [
                    {
                        "created_at": "2021-05-02T00:00:00Z",
                        "group_key": "org:6",
                        "group_properties": {"industry": "technology"},
                        "group_type_index": 0,
                    },
                    {
                        "created_at": "2021-05-01T00:00:00Z",
                        "group_key": "org:5",
                        "group_properties": {
                            "industry": "finance",
                            "name": "Mr. Krabs",
                        },
                        "group_type_index": 0,
                    },
                ],
            },
        )
        response_data = self.client.get(f"/api/projects/{self.team.id}/groups?group_type_index=0&search=Krabs").json()
        self.assertEqual(
            response_data,
            {
                "next": None,
                "previous": None,
                "results": [
                    {
                        "created_at": "2021-05-01T00:00:00Z",
                        "group_key": "org:5",
                        "group_properties": {
                            "industry": "finance",
                            "name": "Mr. Krabs",
                        },
                        "group_type_index": 0,
                    },
                ],
            },
        )

        response_data = self.client.get(f"/api/projects/{self.team.id}/groups?group_type_index=0&search=org:5").json()
        self.assertEqual(
            response_data,
            {
                "next": None,
                "previous": None,
                "results": [
                    {
                        "created_at": "2021-05-01T00:00:00Z",
                        "group_key": "org:5",
                        "group_properties": {
                            "industry": "finance",
                            "name": "Mr. Krabs",
                        },
                        "group_type_index": 0,
                    },
                ],
            },
        )

    @freeze_time("2021-05-02")
    def test_groups_list_no_group_type(self):
        response_data = self.client.get(f"/api/projects/{self.team.id}/groups/").json()
        self.assertEqual(
            response_data,
            {
                "type": "validation_error",
                "attr": "group_type_index",
                "code": "invalid_input",
                "detail": mock.ANY,
            },
        )

    @freeze_time("2021-05-02")
    def test_retrieve_group(self):
        create_group(
            team_id=self.team.pk,
            group_type_index=0,
            group_key="key",
            properties={"industry": "finance", "name": "Mr. Krabs"},
        )
        create_group(
            team_id=self.team.pk,
            group_type_index=1,
            group_key="foo//bar",
            properties={},
        )

        fail_response = self.client.get(f"/api/projects/{self.team.id}/groups/find?group_type_index=1&group_key=key")
        self.assertEqual(fail_response.status_code, 404)

        ok_response_data = self.client.get(f"/api/projects/{self.team.id}/groups/find?group_type_index=0&group_key=key")
        self.assertEqual(ok_response_data.status_code, 200)
        self.assertEqual(
            ok_response_data.json(),
            {
                "created_at": "2021-05-02T00:00:00Z",
                "group_key": "key",
                "group_properties": {"industry": "finance", "name": "Mr. Krabs"},
                "group_type_index": 0,
            },
        )
        ok_response_data = self.client.get(
            f"/api/projects/{self.team.id}/groups/find?group_type_index=1&group_key=foo//bar"
        )
        self.assertEqual(ok_response_data.status_code, 200)
        self.assertEqual(
            ok_response_data.json(),
            {
                "created_at": "2021-05-02T00:00:00Z",
                "group_key": "foo//bar",
                "group_properties": {},
                "group_type_index": 1,
            },
        )

    @freeze_time("2021-05-02")
    @mock.patch("ee.clickhouse.views.groups.capture_internal")
    def test_create_group_missing_group_properties(self, mock_capture):
        group_type_mapping = GroupTypeMapping.objects.create(
            team=self.team,
            project_id=self.team.project_id,
            group_type_index=0,
            group_type="organization",
        )
        group_key = "1234"

        response = self.client.post(
            f"/api/projects/{self.team.id}/groups",
            {
                "group_key": group_key,
                "group_type_index": group_type_mapping.group_type_index,
                "group_properties": None,
            },
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(
            response.json(),
            {
                "created_at": "2021-05-02T00:00:00Z",
                "group_key": group_key,
                "group_properties": {},
                "group_type_index": group_type_mapping.group_type_index,
            },
        )
        mock_capture.assert_called_once()

    @freeze_time("2021-05-02")
    @mock.patch("ee.clickhouse.views.groups.capture_internal")
    @flaky(max_runs=3, min_passes=1)
    def test_create_group(self, mock_capture):
        group_type_mapping = GroupTypeMapping.objects.create(
            team=self.team,
            project_id=self.team.project_id,
            group_type_index=0,
            group_type="organization",
        )
        group_properties = {"name": "Group Name", "industry": "finance"}
        group_key = "1234"

        response = self.client.post(
            f"/api/projects/{self.team.id}/groups",
            {
                "group_key": group_key,
                "group_type_index": group_type_mapping.group_type_index,
                "group_properties": group_properties,
            },
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(
            response.json(),
            {
                "created_at": "2021-05-02T00:00:00Z",
                "group_key": group_key,
                "group_properties": group_properties,
                "group_type_index": 0,
            },
        )
        response = execute_hogql_query(
            parse_select(
                """
                select properties
                from groups
                where index = {index}
                  and key = {key}
                """,
                placeholders={
                    "index": ast.Constant(value=group_type_mapping.group_type_index),
                    "key": ast.Constant(value=group_key),
                },
            ),
            self.team,
        )
        self.assertEqual(response.results, [(json.dumps(group_properties),)])
        mock_capture.assert_called_once_with(
            token=self.team.api_token,
            event_name="$groupidentify",
            event_source="ee_ch_views_groups",
            distinct_id=str(self.team.uuid),
            timestamp=mock.ANY,
            properties={
                "$group_type": group_type_mapping.group_type,
                "$group_key": group_key,
                "$group_set": group_properties,
            },
            process_person_profile=False,
        )

        response = self.client.get(
            f"/api/projects/{self.team.id}/groups/activity?group_key={group_key}&group_type_index=0",
        )

        self.assertEqual(response.status_code, 200)
        results = response.json()["results"]
        self.assertEqual(len(results), 2)
        for result in results:
            self.assertEqual(result["activity"], "create_group")
            self.assertEqual(result["scope"], "Group")
            self.assertEqual(result["detail"]["changes"][0]["action"], "created")
            self.assertIsNone(result["detail"]["changes"][0]["before"])
            prop_name = result["detail"]["name"]
            self.assertEqual(result["detail"]["changes"][0]["after"], group_properties[prop_name])

    @mock.patch("ee.clickhouse.views.groups.capture_internal")
    def test_create_group_duplicated_group_key(self, mock_capture):
        group_type_mapping = GroupTypeMapping.objects.create(
            team=self.team,
            project_id=self.team.project_id,
            group_type_index=0,
            group_type="organization",
        )
        group_key = "1234"
        create_group(
            team_id=self.team.pk,
            group_type_index=group_type_mapping.group_type_index,
            group_key=group_key,
            properties={},
        )

        response = self.client.post(
            f"/api/projects/{self.team.id}/groups",
            {
                "group_key": group_key,
                "group_type_index": 0,
                "group_properties": {},
            },
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.json(),
            {
                "type": "validation_error",
                "code": "invalid_input",
                "detail": "A group with this key already exists",
                "attr": "detail",
            },
        )
        mock_capture.assert_not_called()

    @mock.patch("ee.clickhouse.views.groups.capture_internal")
    def test_create_group_missing_group_key(self, mock_capture):
        group_type_mapping = GroupTypeMapping.objects.create(
            team=self.team,
            project_id=self.team.project_id,
            group_type_index=0,
            group_type="organization",
        )

        response = self.client.post(
            f"/api/projects/{self.team.id}/groups",
            {
                "group_key": None,
                "group_type_index": group_type_mapping.group_type_index,
                "group_properties": {},
            },
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.json(),
            {
                "attr": "group_key",
                "code": "null",
                "detail": "This field may not be null.",
                "type": "validation_error",
            },
        )
        mock_capture.assert_not_called()

    @mock.patch("ee.clickhouse.views.groups.capture_internal")
    def test_create_group_missing_group_type_index(self, mock_capture):
        response = self.client.post(
            f"/api/projects/{self.team.id}/groups",
            {
                "group_key": "foo",
                "group_type_index": None,
                "group_properties": {},
            },
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.json(),
            {
                "attr": "group_type_index",
                "code": "null",
                "detail": "This field may not be null.",
                "type": "validation_error",
            },
        )
        mock_capture.assert_not_called()

    @freeze_time("2021-05-02")
    @mock.patch("ee.clickhouse.views.groups.capture_internal")
    @flaky(max_runs=3, min_passes=1)
    def test_group_property_crud_add_success(self, mock_capture):
        group_type_mapping = GroupTypeMapping.objects.create(
            team=self.team,
            project_id=self.team.project_id,
            group_type_index=0,
            group_type="organization",
        )
        group = create_group(
            team_id=self.team.pk,
            group_type_index=group_type_mapping.group_type_index,
            group_key="org:5",
            properties={"name": "Mr. Krabs"},
        )
        create_group(
            team_id=self.team.pk,
            group_type_index=group_type_mapping.group_type_index,
            group_key="org:55",
            properties={"name": "Mr. Krabs"},
        )

        response = self.client.post(
            f"/api/projects/{self.team.id}/groups/update_property?group_key=org:5&group_type_index=0",
            {"key": "industry", "value": "technology"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "created_at": "2021-05-02T00:00:00Z",
                "group_key": "org:5",
                "group_properties": {"industry": "technology", "name": "Mr. Krabs"},
                "group_type_index": 0,
            },
        )

        response = execute_hogql_query(
            parse_select(
                """
                select properties
                from groups
                where index = {index}
                and key = {key}
                """,
                placeholders={
                    "index": ast.Constant(value=group.group_type_index),
                    "key": ast.Constant(value=group.group_key),
                },
            ),
            self.team,
        )
        self.assertEqual(response.results, [('{"name": "Mr. Krabs", "industry": "technology"}',)])

        mock_capture.assert_called_once_with(
            token=self.team.api_token,
            event_name="$groupidentify",
            event_source="ee_ch_views_groups",
            distinct_id=str(self.team.uuid),
            timestamp=mock.ANY,
            properties={
                "$group_type": group_type_mapping.group_type,
                "$group_key": group.group_key,
                "$group_set": {"industry": "technology"},
            },
            process_person_profile=False,
        )

        response = self.client.get(
            f"/api/projects/{self.team.id}/groups/activity?group_key=org:5&group_type_index=0",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("results", response.json())
        self.assertEqual(len(response.json()["results"]), 1)
        self.assertEqual(response.json()["results"][0]["activity"], "update_property")
        self.assertEqual(response.json()["results"][0]["scope"], "Group")
        self.assertEqual(response.json()["results"][0]["item_id"], str(group.pk))
        self.assertEqual(response.json()["results"][0]["detail"]["changes"][0]["type"], "Group")
        self.assertEqual(response.json()["results"][0]["detail"]["changes"][0]["action"], "created")
        self.assertEqual(response.json()["results"][0]["detail"]["changes"][0]["before"], None)
        self.assertEqual(response.json()["results"][0]["detail"]["changes"][0]["after"], "technology")

    @freeze_time("2021-05-02")
    @mock.patch("ee.clickhouse.views.groups.capture_internal")
    @flaky(max_runs=3, min_passes=1)
    def test_group_property_crud_update_success(self, mock_capture):
        group_type_mapping = GroupTypeMapping.objects.create(
            team=self.team,
            project_id=self.team.project_id,
            group_type_index=0,
            group_type="organization",
        )
        group = create_group(
            team_id=self.team.pk,
            group_type_index=group_type_mapping.group_type_index,
            group_key="org:5",
            properties={"industry": "finance", "name": "Mr. Krabs"},
        )

        response = self.client.post(
            f"/api/projects/{self.team.id}/groups/update_property?group_key=org:5&group_type_index=0",
            {"key": "industry", "value": "technology"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "created_at": "2021-05-02T00:00:00Z",
                "group_key": "org:5",
                "group_properties": {"industry": "technology", "name": "Mr. Krabs"},
                "group_type_index": 0,
            },
        )

        response = execute_hogql_query(
            parse_select(
                """
                select properties
                from groups
                where index = {index}
                and key = {key}
                """,
                placeholders={
                    "index": ast.Constant(value=group.group_type_index),
                    "key": ast.Constant(value=group.group_key),
                },
            ),
            self.team,
        )
        # Check properties regardless of JSON key order
        self.assertEqual(len(response.results), 1)
        self.assertEqual(len(response.results[0]), 1)
        self.assertEqual(orjson.loads(response.results[0][0]), {"name": "Mr. Krabs", "industry": "technology"})

        mock_capture.assert_called_once_with(
            token=self.team.api_token,
            event_name="$groupidentify",
            event_source="ee_ch_views_groups",
            distinct_id=str(self.team.uuid),
            timestamp=mock.ANY,
            properties={
                "$group_type": group_type_mapping.group_type,
                "$group_key": group.group_key,
                "$group_set": {"industry": "technology"},
            },
            process_person_profile=False,
        )

        response = self.client.get(
            f"/api/projects/{self.team.id}/groups/activity?group_key=org:5&group_type_index=0",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("results", response.json())
        self.assertEqual(len(response.json()["results"]), 1)
        self.assertEqual(response.json()["results"][0]["activity"], "update_property")
        self.assertEqual(response.json()["results"][0]["scope"], "Group")
        self.assertEqual(response.json()["results"][0]["item_id"], str(group.pk))
        self.assertEqual(response.json()["results"][0]["detail"]["changes"][0]["type"], "Group")
        self.assertEqual(response.json()["results"][0]["detail"]["changes"][0]["action"], "changed")
        self.assertEqual(response.json()["results"][0]["detail"]["changes"][0]["before"], "finance")
        self.assertEqual(response.json()["results"][0]["detail"]["changes"][0]["after"], "technology")

    @freeze_time("2021-05-02")
    def test_group_property_crud_update_missing_key(self):
        group_type_mapping = GroupTypeMapping.objects.create(
            team=self.team,
            project_id=self.team.project_id,
            group_type_index=0,
            group_type="organization",
        )
        create_group(
            team_id=self.team.pk,
            group_type_index=group_type_mapping.group_type_index,
            group_key="org:5",
            properties={"industry": "finance", "name": "Mr. Krabs"},
        )

        response = self.client.post(
            f"/api/projects/{self.team.id}/groups/update_property?group_key=org:5&group_type_index=0",
            {"value": "technology"},
        )
        self.assertEqual(response.status_code, 400)

    @freeze_time("2021-05-02")
    def test_group_property_crud_update_invalid_group_key(self):
        group_type_mapping = GroupTypeMapping.objects.create(
            team=self.team,
            project_id=self.team.project_id,
            group_type_index=0,
            group_type="organization",
        )
        create_group(
            team_id=self.team.pk,
            group_type_index=group_type_mapping.group_type_index,
            group_key="org:5",
            properties={"industry": "finance", "name": "Mr. Krabs"},
        )

        response = self.client.post(
            f"/api/projects/{self.team.id}/groups/update_property?group_key=org:0&group_type_index=0",
            {"key": "industry", "value": "technology"},
        )
        self.assertEqual(response.status_code, 404)

    @freeze_time("2021-05-02")
    @mock.patch("ee.clickhouse.views.groups.capture_internal")
    @flaky(max_runs=3, min_passes=1)
    def test_group_property_crud_delete_success(self, mock_capture):
        group_type_mapping = GroupTypeMapping.objects.create(
            team=self.team,
            project_id=self.team.project_id,
            group_type_index=0,
            group_type="organization",
        )
        group = create_group(
            team_id=self.team.pk,
            group_type_index=group_type_mapping.group_type_index,
            group_key="org:5",
            properties={"industry": "finance", "name": "Mr. Krabs"},
        )

        response = self.client.post(
            f"/api/projects/{self.team.id}/groups/delete_property?group_key=org:5&group_type_index=0",
            {"$unset": "industry"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "created_at": "2021-05-02T00:00:00Z",
                "group_key": "org:5",
                "group_properties": {"name": "Mr. Krabs"},
                "group_type_index": 0,
            },
        )

        response = execute_hogql_query(
            parse_select(
                """
                select properties
                from groups
                where index = {index}
                and key = {key}
                """,
                placeholders={
                    "index": ast.Constant(value=group.group_type_index),
                    "key": ast.Constant(value=group.group_key),
                },
            ),
            self.team,
        )
        self.assertEqual(response.results, [('{"name": "Mr. Krabs"}',)])

        mock_capture.assert_called_once_with(
            token=self.team.api_token,
            event_name="$delete_group_property",
            event_source="ee_ch_views_groups",
            distinct_id=str(self.team.uuid),
            timestamp=mock.ANY,
            properties={
                "$group_type": group_type_mapping.group_type,
                "$group_key": group.group_key,
                "$group_unset": ["industry"],
            },
            process_person_profile=False,
        )

        response = self.client.get(
            f"/api/projects/{self.team.id}/groups/activity?group_key=org:5&group_type_index=0",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("results", response.json())
        self.assertEqual(len(response.json()["results"]), 1)
        self.assertEqual(response.json()["results"][0]["activity"], "update_property")
        self.assertEqual(response.json()["results"][0]["scope"], "Group")
        self.assertEqual(response.json()["results"][0]["item_id"], str(group.pk))
        self.assertEqual(response.json()["results"][0]["detail"]["changes"][0]["type"], "Group")
        self.assertEqual(response.json()["results"][0]["detail"]["changes"][0]["action"], "deleted")
        self.assertEqual(response.json()["results"][0]["detail"]["changes"][0]["before"], "finance")
        self.assertEqual(response.json()["results"][0]["detail"]["changes"][0]["after"], None)

    @freeze_time("2021-05-02")
    def test_group_property_crud_delete_missing_key(self):
        group_type_mapping = GroupTypeMapping.objects.create(
            team=self.team,
            project_id=self.team.project_id,
            group_type_index=0,
            group_type="organization",
        )
        create_group(
            team_id=self.team.pk,
            group_type_index=group_type_mapping.group_type_index,
            group_key="org:5",
            properties={"industry": "finance", "name": "Mr. Krabs"},
        )

        response = self.client.post(
            f"/api/projects/{self.team.id}/groups/delete_property?group_key=org:5&group_type_index=0",
            {},
        )
        self.assertEqual(response.status_code, 400)

    @freeze_time("2021-05-02")
    def test_group_property_crud_delete_invalid_group_key(self):
        group_type_mapping = GroupTypeMapping.objects.create(
            team=self.team,
            project_id=self.team.project_id,
            group_type_index=0,
            group_type="organization",
        )
        create_group(
            team_id=self.team.pk,
            group_type_index=group_type_mapping.group_type_index,
            group_key="org:5",
            properties={"industry": "finance", "name": "Mr. Krabs"},
        )

        response = self.client.post(
            f"/api/projects/{self.team.id}/groups/delete_property?group_key=org:0&group_type_index=0",
            {"$unset": "industry"},
        )
        self.assertEqual(response.status_code, 404)

    @freeze_time("2021-05-02")
    @patch("ee.clickhouse.views.groups.capture_internal")
    def test_get_group_activities_success(self, mock_capture):
        # Mock the response to return a 200 OK
        mock_capture.return_value = mock.MagicMock(status_code=200)

        group_type_mapping = GroupTypeMapping.objects.create(
            team=self.team,
            project_id=self.team.project_id,
            group_type_index=0,
            group_type="organization",
        )
        group = create_group(
            team_id=self.team.pk,
            group_type_index=group_type_mapping.group_type_index,
            group_key="org:5",
            properties={"industry": "finance", "name": "Mr. Krabs"},
        )

        # Triggers the entry
        response = self.client.post(
            f"/api/projects/{self.team.id}/groups/update_property?group_key=org:5&group_type_index=0",
            {"key": "industry", "value": "technology"},
        )

        self.assertEqual(response.status_code, 200)

        response = self.client.get(
            f"/api/projects/{self.team.id}/groups/activity?group_key=org:5&group_type_index=0",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("results", response.json())
        self.assertEqual(len(response.json()["results"]), 1)
        self.assertEqual(response.json()["results"][0]["activity"], "update_property")
        self.assertEqual(response.json()["results"][0]["scope"], "Group")
        self.assertEqual(response.json()["results"][0]["item_id"], str(group.pk))
        self.assertEqual(response.json()["results"][0]["detail"]["changes"][0]["type"], "Group")
        self.assertEqual(response.json()["results"][0]["detail"]["changes"][0]["action"], "changed")

    @freeze_time("2021-05-02")
    @patch("ee.clickhouse.views.groups.capture_internal")
    def test_get_group_activities_invalid_group(self, mock_capture):
        # Mock the response to return a 200 OK
        mock_capture.return_value = mock.MagicMock(status_code=200)

        group_type_mapping = GroupTypeMapping.objects.create(
            team=self.team,
            project_id=self.team.project_id,
            group_type_index=0,
            group_type="organization",
        )
        create_group(
            team_id=self.team.pk,
            group_type_index=group_type_mapping.group_type_index,
            group_key="org:5",
            properties={"industry": "finance", "name": "Mr. Krabs"},
        )

        # Triggers the entry
        response = self.client.post(
            f"/api/projects/{self.team.id}/groups/update_property?group_key=org:5&group_type_index=0",
            {"key": "industry", "value": "technology"},
        )

        self.assertEqual(response.status_code, 200)

        response = self.client.get(
            f"/api/projects/{self.team.id}/groups/activity?group_key=org:5&group_type_index=1",
        )

        self.assertEqual(response.status_code, 404)

    @freeze_time("2021-05-10")
    @snapshot_clickhouse_queries
    def test_related_groups(self):
        self._create_related_groups_data()

        response_data = self.client.get(
            f"/api/projects/{self.team.id}/groups/related?id=0::0&group_type_index=0"
        ).json()
        self.assertEqual(
            response_data,
            [
                {
                    "created_at": "2021-05-10T00:00:00Z",
                    "distinct_ids": ["1", "2"],
                    "id": "01795392-cc00-0003-7dc7-67a694604d72",
                    "uuid": "01795392-cc00-0003-7dc7-67a694604d72",
                    "is_identified": False,
                    "name": "1",
                    "properties": {},
                    "type": "person",
                    "matched_recordings": [],
                    "value_at_data_point": None,
                },
                {
                    "created_at": "2021-05-10T00:00:00Z",
                    "group_key": "1::2",
                    "group_type_index": 1,
                    "id": "1::2",
                    "properties": {},
                    "type": "group",
                    "matched_recordings": [],
                    "value_at_data_point": None,
                },
                {
                    "created_at": "2021-05-10T00:00:00Z",
                    "group_key": "1::3",
                    "group_type_index": 1,
                    "id": "1::3",
                    "properties": {},
                    "type": "group",
                    "matched_recordings": [],
                    "value_at_data_point": None,
                },
            ],
        )

    @freeze_time("2021-05-10")
    @snapshot_clickhouse_queries
    def test_related_groups_person(self):
        uuid = self._create_related_groups_data()

        response_data = self.client.get(f"/api/projects/{self.team.id}/groups/related?id={uuid}").json()
        self.assertEqual(
            response_data,
            [
                {
                    "created_at": "2021-05-10T00:00:00Z",
                    "group_key": "0::0",
                    "group_type_index": 0,
                    "id": "0::0",
                    "properties": {},
                    "type": "group",
                    "matched_recordings": [],
                    "value_at_data_point": None,
                },
                {
                    "created_at": "2021-05-10T00:00:00Z",
                    "group_key": "0::1",
                    "group_type_index": 0,
                    "id": "0::1",
                    "properties": {},
                    "type": "group",
                    "matched_recordings": [],
                    "value_at_data_point": None,
                },
                {
                    "created_at": "2021-05-10T00:00:00Z",
                    "group_key": "1::2",
                    "group_type_index": 1,
                    "id": "1::2",
                    "properties": {},
                    "type": "group",
                    "matched_recordings": [],
                    "value_at_data_point": None,
                },
                {
                    "created_at": "2021-05-10T00:00:00Z",
                    "group_key": "1::3",
                    "group_type_index": 1,
                    "id": "1::3",
                    "properties": {},
                    "type": "group",
                    "matched_recordings": [],
                    "value_at_data_point": None,
                },
            ],
        )

    def test_property_definitions(self):
        create_group(
            team_id=self.team.pk,
            group_type_index=0,
            group_key="org:5",
            properties={"industry": "finance", "name": "Mr. Krabs"},
        )
        create_group(
            team_id=self.team.pk,
            group_type_index=0,
            group_key="org:6",
            properties={"industry": "technology"},
        )
        create_group(
            team_id=self.team.pk,
            group_type_index=1,
            group_key="company:1",
            properties={"name": "Plankton"},
        )
        create_group(
            team_id=self.team.pk,
            group_type_index=1,
            group_key="company:2",
            properties={},
        )

        response_data = self.client.get(f"/api/projects/{self.team.id}/groups/property_definitions").json()
        self.assertEqual(
            response_data,
            {
                "0": [{"name": "industry", "count": 2}, {"name": "name", "count": 1}],
                "1": [{"name": "name", "count": 1}],
            },
        )

    def test_property_values(self):
        create_group(
            team_id=self.team.pk,
            group_type_index=0,
            group_key="org:5",
            properties={"industry": "finance"},
        )
        create_group(
            team_id=self.team.pk,
            group_type_index=0,
            group_key="org:6",
            properties={"industry": "technology"},
        )
        create_group(
            team_id=self.team.pk,
            group_type_index=0,
            group_key="org:7",
            properties={"industry": "finance-technology"},
        )
        create_group(
            team_id=self.team.pk,
            group_type_index=1,
            group_key="org:1",
            properties={"industry": "finance"},
        )

        # Test without query parameter
        response_data = self.client.get(
            f"/api/projects/{self.team.id}/groups/property_values/?key=industry&group_type_index=0"
        ).json()
        self.assertEqual(len(response_data), 3)
        self.assertEqual(
            response_data,
            [
                {"name": "finance", "count": 1},
                {"name": "finance-technology", "count": 1},
                {"name": "technology", "count": 1},
            ],
        )

        # Test with query parameter
        response_data = self.client.get(
            f"/api/projects/{self.team.id}/groups/property_values/?key=industry&group_type_index=0&value=fin"
        ).json()
        self.assertEqual(len(response_data), 2)
        self.assertEqual(response_data, [{"name": "finance", "count": 1}, {"name": "finance-technology", "count": 1}])

        # Test with query parameter - case insensitive
        response_data = self.client.get(
            f"/api/projects/{self.team.id}/groups/property_values/?key=industry&group_type_index=0&value=TECH"
        ).json()
        self.assertEqual(len(response_data), 2)
        self.assertEqual(
            response_data, [{"name": "finance-technology", "count": 1}, {"name": "technology", "count": 1}]
        )

        # Test with query parameter - no matches
        response_data = self.client.get(
            f"/api/projects/{self.team.id}/groups/property_values/?key=industry&group_type_index=0&value=healthcare"
        ).json()
        self.assertEqual(len(response_data), 0)
        self.assertEqual(response_data, [])

        # Test with query parameter - exact match
        response_data = self.client.get(
            f"/api/projects/{self.team.id}/groups/property_values/?key=industry&group_type_index=0&value=technology"
        ).json()
        self.assertEqual(len(response_data), 2)
        self.assertEqual(
            response_data, [{"name": "finance-technology", "count": 1}, {"name": "technology", "count": 1}]
        )

        # Test with different group_type_index
        response_data = self.client.get(
            f"/api/projects/{self.team.id}/groups/property_values/?key=industry&group_type_index=1&value=fin"
        ).json()
        self.assertEqual(len(response_data), 1)
        self.assertEqual(response_data, [{"name": "finance", "count": 1}])

    def test_empty_property_values(self):
        create_group(
            team_id=self.team.pk,
            group_type_index=0,
            group_key="org:5",
            properties={"industry": "finance"},
        )
        create_group(
            team_id=self.team.pk,
            group_type_index=0,
            group_key="org:6",
            properties={"industry": "technology"},
        )
        create_group(
            team_id=self.team.pk,
            group_type_index=1,
            group_key="org:1",
            properties={"industry": "finance"},
        )
        response_data = self.client.get(
            f"/api/projects/{self.team.id}/groups/property_values/?key=name&group_type_index=0"
        ).json()
        self.assertEqual(len(response_data), 0)
        self.assertEqual(response_data, [])

    def test_update_groups_metadata(self):
        GroupTypeMapping.objects.create(
            team=self.team, project_id=self.team.project_id, group_type="organization", group_type_index=0
        )
        GroupTypeMapping.objects.create(
            team=self.team, project_id=self.team.project_id, group_type="playlist", group_type_index=1
        )
        GroupTypeMapping.objects.create(
            team=self.team, project_id=self.team.project_id, group_type="another", group_type_index=2
        )

        response_data = self.client.patch(
            f"/api/projects/{self.team.id}/groups_types/update_metadata",
            [
                {"group_type_index": 0, "name_singular": "organization!"},
                {
                    "group_type_index": 1,
                    "group_type": "rename attempt",
                    "name_plural": "playlists",
                },
            ],
        ).json()

        self.assertEqual(
            response_data,
            [
                {
                    "group_type_index": 0,
                    "group_type": "organization",
                    "name_singular": "organization!",
                    "name_plural": None,
                    "detail_dashboard": None,
                    "default_columns": None,
                },
                {
                    "group_type_index": 1,
                    "group_type": "playlist",
                    "name_singular": None,
                    "name_plural": "playlists",
                    "detail_dashboard": None,
                    "default_columns": None,
                },
                {
                    "group_type_index": 2,
                    "group_type": "another",
                    "name_singular": None,
                    "name_plural": None,
                    "detail_dashboard": None,
                    "default_columns": None,
                },
            ],
        )

    def test_list_group_types(self):
        GroupTypeMapping.objects.create(
            team=self.team, project_id=self.team.project_id, group_type="organization", group_type_index=0
        )
        GroupTypeMapping.objects.create(
            team=self.team, project_id=self.team.project_id, group_type="playlist", group_type_index=1
        )
        GroupTypeMapping.objects.create(
            team=self.team, project_id=self.team.project_id, group_type="another", group_type_index=2
        )

        response_data = self.client.get(f"/api/projects/{self.team.id}/groups_types").json()

        self.assertEqual(
            response_data,
            [
                {
                    "group_type_index": 0,
                    "group_type": "organization",
                    "name_singular": None,
                    "name_plural": None,
                    "detail_dashboard": None,
                    "default_columns": None,
                },
                {
                    "group_type_index": 1,
                    "group_type": "playlist",
                    "name_singular": None,
                    "name_plural": None,
                    "detail_dashboard": None,
                    "default_columns": None,
                },
                {
                    "group_type_index": 2,
                    "group_type": "another",
                    "name_singular": None,
                    "name_plural": None,
                    "detail_dashboard": None,
                    "default_columns": None,
                },
            ],
        )

    def test_cannot_list_group_types_of_another_org(self):
        other_org = Organization.objects.create(name="other org")
        other_team = Team.objects.create(organization=other_org, name="other project")

        GroupTypeMapping.objects.create(
            team=other_team, project_id=other_team.project_id, group_type="organization", group_type_index=0
        )
        GroupTypeMapping.objects.create(
            team=other_team, project_id=other_team.project_id, group_type="playlist", group_type_index=1
        )
        GroupTypeMapping.objects.create(
            team=other_team, project_id=other_team.project_id, group_type="another", group_type_index=2
        )

        response = self.client.get(f"/api/projects/{other_team.id}/groups_types")  # No access to this project

        self.assertEqual(response.status_code, 403, response.json())
        self.assertEqual(
            response.json(),
            self.permission_denied_response("You don't have access to the project."),
        )

    def test_cannot_list_group_types_of_another_org_with_sharing_token(self):
        sharing_configuration = SharingConfiguration.objects.create(team=self.team, enabled=True)

        other_org = Organization.objects.create(name="other org")
        other_team = Team.objects.create(organization=other_org, name="other project")

        GroupTypeMapping.objects.create(
            team=other_team, project_id=other_team.project_id, group_type="organization", group_type_index=0
        )
        GroupTypeMapping.objects.create(
            team=other_team, project_id=other_team.project_id, group_type="playlist", group_type_index=1
        )
        GroupTypeMapping.objects.create(
            team=other_team, project_id=other_team.project_id, group_type="another", group_type_index=2
        )

        response = self.client.get(
            f"/api/projects/{other_team.id}/groups_types/?sharing_access_token={sharing_configuration.access_token}"
        )

        self.assertEqual(response.status_code, 403, response.json())
        self.assertEqual(
            response.json(),
            self.permission_denied_response("You do not have permission to perform this action."),
        )

    def test_can_list_group_types_of_another_org_with_sharing_access_token(self):
        other_org = Organization.objects.create(name="other org")
        other_team = Team.objects.create(organization=other_org, name="other project")
        sharing_configuration = SharingConfiguration.objects.create(team=other_team, enabled=True)

        GroupTypeMapping.objects.create(
            team=other_team, project_id=other_team.project_id, group_type="organization", group_type_index=0
        )
        GroupTypeMapping.objects.create(
            team=other_team, project_id=other_team.project_id, group_type="playlist", group_type_index=1
        )
        GroupTypeMapping.objects.create(
            team=other_team, project_id=other_team.project_id, group_type="another", group_type_index=2
        )

        disabled_response = self.client.get(
            f"/api/projects/{other_team.id}/groups_types/?sharing_access_token={sharing_configuration.access_token}"
        ).json()

        self.assertEqual(
            disabled_response,
            [
                {
                    "group_type_index": 0,
                    "group_type": "organization",
                    "name_singular": None,
                    "name_plural": None,
                    "detail_dashboard": None,
                    "default_columns": None,
                },
                {
                    "group_type_index": 1,
                    "group_type": "playlist",
                    "name_singular": None,
                    "name_plural": None,
                    "detail_dashboard": None,
                    "default_columns": None,
                },
                {
                    "group_type_index": 2,
                    "group_type": "another",
                    "name_singular": None,
                    "name_plural": None,
                    "detail_dashboard": None,
                    "default_columns": None,
                },
            ],
        )

        # Disable the config now
        sharing_configuration.enabled = False
        sharing_configuration.save()

        disabled_response = self.client.get(
            f"/api/projects/{other_team.id}/groups_types?sharing_access_token={sharing_configuration.access_token}"
        )

        self.assertEqual(disabled_response.status_code, 403, disabled_response.json())
        self.assertEqual(
            disabled_response.json(),
            self.unauthenticated_response("Sharing access token is invalid.", "authentication_failed"),
        )

    def test_create_detail_dashboard_success(self):
        group_type_mapping = GroupTypeMapping.objects.create(
            team=self.team, project_id=self.team.project_id, group_type="organization", group_type_index=0
        )

        response = self.client.put(
            f"/api/projects/{self.team.id}/groups_types/create_detail_dashboard",
            {"group_type_index": 0},
        )
        self.assertEqual(response.status_code, 200)

        group_type_mapping.refresh_from_db()
        self.assertIsNotNone(group_type_mapping.detail_dashboard)

    def test_create_detail_dashboard_duplicate(self):
        group_type = GroupTypeMapping.objects.create(
            team=self.team, project_id=self.team.project_id, group_type="organization", group_type_index=0
        )

        dashboard = create_group_type_mapping_detail_dashboard(group_type, self.user)
        group_type.detail_dashboard = dashboard
        group_type.save()

        response = self.client.put(
            f"/api/projects/{self.team.id}/groups_types/create_detail_dashboard",
            {"group_type_index": 0},
        )
        self.assertEqual(response.status_code, 400)

    def test_create_detail_dashboard_not_found(self):
        response = self.client.put(
            f"/api/projects/{self.team.id}/groups_types/create_detail_dashboard",
            {"group_type_index": 1},
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json().get("detail"), "Group type not found")

    def test_set_default_columns_success(self):
        group_type_mapping = GroupTypeMapping.objects.create(
            team=self.team, project_id=self.team.project_id, group_type="organization", group_type_index=0
        )

        response = self.client.put(
            f"/api/projects/{self.team.id}/groups_types/set_default_columns",
            {"group_type_index": 0, "default_columns": ["$group_0", "$group_1"]},
        )
        self.assertEqual(response.status_code, 200)

        group_type_mapping.refresh_from_db()
        self.assertEqual(group_type_mapping.default_columns, ["$group_0", "$group_1"])

    def test_set_default_columns_not_found(self):
        response = self.client.put(
            f"/api/projects/{self.team.id}/groups_types/set_default_columns",
            {"group_type_index": 1, "default_columns": ["$group_0", "$group_1"]},
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json().get("detail"), "Group type not found")

    def _create_related_groups_data(self):
        GroupTypeMapping.objects.create(
            team=self.team, project_id=self.team.project_id, group_type="organization", group_type_index=0
        )
        GroupTypeMapping.objects.create(
            team=self.team, project_id=self.team.project_id, group_type="playlist", group_type_index=1
        )

        uuid = UUID("01795392-cc00-0003-7dc7-67a694604d72")

        Person.objects.create(uuid=uuid, team_id=self.team.pk, distinct_ids=["1", "2"])
        Person.objects.create(team_id=self.team.pk, distinct_ids=["3"])
        Person.objects.create(team_id=self.team.pk, distinct_ids=["4"])

        create_group(self.team.pk, 0, "0::0")
        create_group(self.team.pk, 0, "0::1")
        create_group(self.team.pk, 1, "1::2")
        create_group(self.team.pk, 1, "1::3")
        create_group(self.team.pk, 1, "1::4")
        create_group(self.team.pk, 1, "1::5")

        _create_event(
            event="$pageview",
            team=self.team,
            distinct_id="1",
            timestamp="2021-05-05 00:00:00",
            properties={"$group_0": "0::0", "$group_1": "1::2"},
        )

        _create_event(
            event="$pageview",
            team=self.team,
            distinct_id="1",
            timestamp="2021-05-05 00:00:00",
            properties={"$group_0": "0::0", "$group_1": "1::3"},
        )

        _create_event(
            event="$pageview",
            team=self.team,
            distinct_id="1",
            timestamp="2021-05-05 00:00:00",
            properties={"$group_0": "0::1", "$group_1": "1::3"},
        )

        # Event too old, not counted
        _create_event(
            event="$pageview",
            team=self.team,
            distinct_id="1",
            timestamp="2000-05-05 00:00:00",
            properties={"$group_0": "0::0", "$group_1": "1::4"},
        )

        # No such group exists in groups table
        _create_event(
            event="$pageview",
            team=self.team,
            distinct_id="1",
            timestamp="2000-05-05 00:00:00",
            properties={"$group_0": "0::0", "$group_1": "no such group"},
        )

        return uuid
