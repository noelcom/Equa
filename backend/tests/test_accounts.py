"""Kontoradering (#14): analyser, filer, profil och auth-användare försvinner, loggen finns kvar."""

import pytest
from helpers import make_pdf

from equa_backend.accounts import delete_account


def _create(client, user, n=1):
    ids = []
    for i in range(n):
        res = client.post(
            "/analyses",
            headers=user.auth,
            data={"title": f"Analys {i}", "job_ad": "Vi söker en utvecklare."},
            files=[("files", (f"cv{i}.pdf", make_pdf(f"CV {i}"), "application/pdf"))],
        )
        assert res.status_code == 201, res.text
        ids.append(res.json()["id"])
    return ids


def _paths(admin, user_id: str) -> list[str]:
    rows = (
        admin.table("analysis_batches")
        .select("candidates(original_path)")
        .eq("user_id", user_id)
        .execute()
        .data
    )
    return [c["original_path"] for a in rows for c in a["candidates"]]


def _file_exists(admin, path: str) -> bool:
    folder, name = path.rsplit("/", 1)
    return any(f["name"] == name for f in admin.storage.from_("originals").list(folder))


def _user_exists(admin, user_id: str) -> bool:
    return any(u.id == user_id for u in admin.auth.admin.list_users(per_page=1000))


class _FailingStorage:
    """Storage där borttagning alltid misslyckas, i övrigt som den riktiga."""

    def __init__(self, real):
        self._real = real

    def from_(self, bucket):
        outer = self._real.from_(bucket)

        class Bucket:
            def __getattr__(self, name):
                return getattr(outer, name)

            def remove(self, paths):
                raise RuntimeError("Storage nere")

        return Bucket()


class _ClientWithFailingStorage:
    def __init__(self, real):
        self._real = real
        self.storage = _FailingStorage(real.storage)

    def __getattr__(self, name):
        return getattr(self._real, name)


def test_account_deletion_removes_everything_but_keeps_the_usage_log(
    client, make_user, admin
):
    user, other = make_user(), make_user()
    _create(client, user, n=2)
    other_ids = _create(client, other)
    paths = _paths(admin, user.id)
    assert len(paths) == 2 and all(_file_exists(admin, p) for p in paths)
    admin.table("usage_logs").insert(
        {"customer_id": user.id, "cv_count": 1, "input_tokens": 10, "output_tokens": 5}
    ).execute()

    assert delete_account(admin, user.id) == 2

    assert (
        admin.table("analysis_batches")
        .select("id")
        .eq("user_id", user.id)
        .execute()
        .data
        == []
    )
    assert not any(_file_exists(admin, p) for p in paths)
    assert admin.table("profiles").select("id").eq("id", user.id).execute().data == []
    assert not _user_exists(admin, user.id)
    logs = (
        admin.table("usage_logs")
        .select("cv_count")
        .eq("customer_id", user.id)
        .execute()
        .data
    )
    assert logs == [{"cv_count": 1}]
    # Andra konton rörs inte.
    assert (
        client.get(f"/analyses/{other_ids[0]}", headers=other.auth).status_code == 200
    )


def test_failed_file_deletion_stops_and_leaves_the_account_and_no_orphaned_files(
    client, make_user, admin
):
    user = make_user()
    _create(client, user, n=2)
    paths = _paths(admin, user.id)
    # Profilen skapas vid första inloggning (anropet ovan), så den finns att bevara.
    assert admin.table("profiles").select("id").eq("id", user.id).execute().data

    with pytest.raises(RuntimeError):
        delete_account(_ClientWithFailingStorage(admin), user.id)

    assert _user_exists(admin, user.id)
    # Raderna finns kvar och pekar på filerna, så en ny körning hittar dem.
    assert sorted(_paths(admin, user.id)) == sorted(paths)
    assert all(_file_exists(admin, p) for p in paths)

    # Ny körning efter felet raderar resten.
    delete_account(admin, user.id)
    assert not any(_file_exists(admin, p) for p in paths)
    assert not _user_exists(admin, user.id)


def test_rerun_works_when_files_are_already_gone_but_rows_remain(
    client, make_user, admin
):
    user = make_user()
    _create(client, user)
    paths = _paths(admin, user.id)
    # Läget efter ett avbrott mellan filradering och radradering.
    admin.storage.from_("originals").remove(paths)

    delete_account(admin, user.id)

    assert (
        admin.table("analysis_batches")
        .select("id")
        .eq("user_id", user.id)
        .execute()
        .data
        == []
    )
    assert not _user_exists(admin, user.id)
