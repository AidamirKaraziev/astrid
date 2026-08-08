"""Награда за приглашённого: приветствие сразу, звёзды пригласившему — за возвращение."""

from __future__ import annotations

import pytest

from astra.core.config import get_settings
from astra.referrals import crud as referrals_crud
from astra.referrals.models import ReferralStatus
from astra.services.referral_service import (
    apply_referral_on_start,
    grant_invitee_welcome,
    reward_referrer_on_return,
)
from astra.wallet import crud as wallet_crud

from conftest import new_test_telegram_id

pytestmark = pytest.mark.asyncio


async def _user(session):
    from astra.users import crud as users_crud

    user = await users_crud.create_user(
        session,
        telegram_id=new_test_telegram_id(),
        username=None,
        language_code="ru",
    )
    await session.flush()
    return user


async def _linked_pair(session):
    """Пригласивший с кодом и пришедший по нему новичок."""
    inviter = await _user(session)
    code = await referrals_crud.get_or_create_referral_code(session, inviter.id)
    invitee = await _user(session)
    await apply_referral_on_start(session, invitee, code.code)
    return inviter, invitee


class TestInviteeWelcome:
    async def test_newcomer_gets_welcome_stars(self, db_session) -> None:
        _, invitee = await _linked_pair(db_session)

        granted = await grant_invitee_welcome(db_session, invitee)

        assert granted == get_settings().referral_welcome_stars
        assert await wallet_crud.get_balance(db_session, invitee.id) == granted

    async def test_welcome_is_paid_once(self, db_session) -> None:
        """Онбординг может доиграть повторно — второй раз платить нельзя."""
        _, invitee = await _linked_pair(db_session)

        first = await grant_invitee_welcome(db_session, invitee)
        second = await grant_invitee_welcome(db_session, invitee)

        assert second == 0
        assert await wallet_crud.get_balance(db_session, invitee.id) == first

    async def test_nothing_for_a_person_without_referral(self, db_session) -> None:
        user = await _user(db_session)
        assert await grant_invitee_welcome(db_session, user) == 0


class TestReferrerReward:
    async def test_reward_lands_on_return(self, db_session) -> None:
        inviter, invitee = await _linked_pair(db_session)

        paid = await reward_referrer_on_return(db_session, invitee)

        assert paid == get_settings().referral_reward_stars
        assert await wallet_crud.get_balance(db_session, inviter.id) == paid

    async def test_reward_is_paid_once(self, db_session) -> None:
        """Приглашение переходит в REWARDED — третий день ничего не добавляет."""
        inviter, invitee = await _linked_pair(db_session)

        first = await reward_referrer_on_return(db_session, invitee)
        second = await reward_referrer_on_return(db_session, invitee)

        assert second == 0
        assert await wallet_crud.get_balance(db_session, inviter.id) == first

    async def test_referral_becomes_rewarded(self, db_session) -> None:
        inviter, invitee = await _linked_pair(db_session)

        await reward_referrer_on_return(db_session, invitee)

        assert await referrals_crud.count_referrals(db_session, inviter.id) == 1
        pending = await referrals_crud.get_pending_referral_for_invitee(db_session, invitee.id)
        assert pending is None

    async def test_self_invite_is_not_linked(self, db_session) -> None:
        """Своя же ссылка не создаёт приглашения — и награждать некого."""
        user = await _user(db_session)
        code = await referrals_crud.get_or_create_referral_code(db_session, user.id)

        await apply_referral_on_start(db_session, user, code.code)

        assert await reward_referrer_on_return(db_session, user) == 0
        assert await wallet_crud.get_balance(db_session, user.id) == 0

    async def test_welcome_and_reward_go_to_different_people(self, db_session) -> None:
        inviter, invitee = await _linked_pair(db_session)
        cfg = get_settings()

        await grant_invitee_welcome(db_session, invitee)
        await reward_referrer_on_return(db_session, invitee)

        assert await wallet_crud.get_balance(db_session, invitee.id) == cfg.referral_welcome_stars
        assert await wallet_crud.get_balance(db_session, inviter.id) == cfg.referral_reward_stars

    async def test_referral_status_is_pending_until_return(self, db_session) -> None:
        _, invitee = await _linked_pair(db_session)
        await grant_invitee_welcome(db_session, invitee)

        referral = await referrals_crud.get_pending_referral_for_invitee(db_session, invitee.id)

        assert referral is not None
        assert referral.status is ReferralStatus.PENDING
