"""Приглашения: привязка по ссылке, приветствие новичку, награда пригласившему.

Награда за приведённого капает **не за регистрацию, а за возвращение**. Раньше
она начислялась в момент, когда новичок закончил онбординг, — то есть за сам
факт появления аккаунта. При безлимитных приглашениях это прямой стимул
заводить пустые аккаунты: одна голова окупалась одним заходом. Возвращение на
следующий день стоит фейку второго дня и делает накрутку заметно дороже.

Начисления идемпотентны по `payload` записи кошелька: онбординг и отметка
активности зовутся из разных мест и в принципе могут повториться.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from astra.core.config import Settings, get_settings
from astra.core.observability import Event, get_logger
from astra.referrals import crud as referrals_crud
from astra.referrals.models import Referral, ReferralStatus
from astra.users.models import User
from astra.wallet import crud as wallet_crud
from astra.wallet.models import WalletReason

log = get_logger(__name__)


def _welcome_payload(referral: Referral) -> str:
    return f"ref_welcome:{referral.id}"


# Начало payload у наград пригласившему. По нему считается «заработано на
# друзьях»: приветствие новичку и подарок носят ту же причину в леджере, и
# сумма по причине смешала бы заработанное с полученным.
REWARD_PAYLOAD_PREFIX = "ref_reward:"


def _reward_payload(referral: Referral) -> str:
    return f"{REWARD_PAYLOAD_PREFIX}{referral.id}"


async def referral_earnings(session: AsyncSession, user_id: UUID) -> int:
    """Сколько звёзд человек заработал именно приглашениями."""
    return await wallet_crud.sum_by_payload_prefix(session, user_id, REWARD_PAYLOAD_PREFIX)


async def apply_referral_on_start(
    session: AsyncSession,
    invitee: User,
    referral_code: str,
) -> None:
    code_row = await referrals_crud.get_referral_code_by_code(session, referral_code)
    if code_row is None or code_row.user_id == invitee.id:
        return
    await referrals_crud.create_referral(
        session,
        referrer_id=code_row.user_id,
        invitee_id=invitee.id,
    )


async def grant_invitee_welcome(
    session: AsyncSession,
    invitee: User,
    settings: Settings | None = None,
) -> int:
    """Приветственные звёзды новичку, пришедшему по ссылке. Сразу после онбординга.

    Статус приглашения не трогаем: пригласивший получит своё, когда новичок
    вернётся во второй день.
    """
    cfg = settings or get_settings()
    if cfg.referral_welcome_stars <= 0:
        return 0
    referral = await referrals_crud.get_pending_referral_for_invitee(session, invitee.id)
    if referral is None:
        return 0

    payload = _welcome_payload(referral)
    already = await wallet_crud.find_by_payload(
        session,
        invitee.id,
        payload,
        WalletReason.REFERRAL_REWARD,
    )
    if already is not None:
        return 0

    await wallet_crud.add_entry(
        session,
        invitee.id,
        cfg.referral_welcome_stars,
        WalletReason.REFERRAL_REWARD,
        description="Добро пожаловать по приглашению",
        payload=payload,
    )
    log.info(
        Event.WALLET_CREDITED,
        user_id=invitee.id,
        amount=cfg.referral_welcome_stars,
        reason="referral_welcome",
    )
    return cfg.referral_welcome_stars


async def reward_referrer_on_return(
    session: AsyncSession,
    invitee: User,
    settings: Settings | None = None,
) -> int:
    """Наградить пригласившего: новичок вернулся, приглашение состоялось.

    Зовётся из отметки активности только во второй и последующие дни жизни
    новичка, поэтому проверять «первый ли это день» здесь не нужно — достаточно
    того, что приглашение ещё в статусе PENDING.
    """
    cfg = settings or get_settings()
    referral = await referrals_crud.get_pending_referral_for_invitee(session, invitee.id)
    if referral is None:
        return 0

    from astra.users import crud as users_crud

    referrer = await users_crud.get_user_by_id(session, referral.referrer_id)
    if referrer is None:
        return 0

    if cfg.referral_reward_stars > 0:
        await wallet_crud.add_entry(
            session,
            referrer.id,
            cfg.referral_reward_stars,
            WalletReason.REFERRAL_REWARD,
            description="Друг вернулся — приглашение состоялось",
            payload=_reward_payload(referral),
        )
    referral.status = ReferralStatus.REWARDED
    referral.rewarded_at = datetime.now(UTC)
    await session.flush()
    log.info(
        Event.WALLET_CREDITED,
        user_id=referrer.id,
        amount=cfg.referral_reward_stars,
        reason="referral_reward",
        invitee_id=invitee.id,
    )
    return cfg.referral_reward_stars
