"""Typed request and response models from the shared wire contract."""

from __future__ import annotations
import base64
from dataclasses import dataclass, field
from collections.abc import Iterator
from typing import Any, Literal, TypeAlias
from ._codec import UNSET, UnsetType, encode


AccountType: TypeAlias = Literal["NATURAL", "JURISTIC"]
QrType: TypeAlias = Literal["PROMPTPAY", "BILL_PAYMENT", "KSHOP", "MAE_MANEE", "TUNGNGERN"]


@dataclass(kw_only=True)
class Model:
    """Wire model; metadata is excluded from representation and JSON."""

    meta: ResponseMeta | None = field(
        default=None, init=False, repr=False, compare=False, metadata={"ignore": True}
    )

    def to_dict(self) -> Any:
        """Return wire JSON with absent fields omitted."""
        return encode(self)


@dataclass(kw_only=True)
class Info(Model):
    """Info wire fields. Unknown enum strings are preserved."""

    application: InfoApplication = field(metadata={"wire": "application"})
    branch: InfoBranch = field(metadata={"wire": "branch"})
    account: InfoAccount = field(metadata={"wire": "account"})
    product: InfoProduct = field(metadata={"wire": "product"})


@dataclass(kw_only=True)
class InfoApplication(Model):
    """InfoApplication wire fields. Unknown enum strings are preserved."""

    name: str = field(metadata={"wire": "name"})
    auto_renew: AutoRenew = field(metadata={"wire": "autoRenew"})
    quota: ApplicationQuota = field(metadata={"wire": "quota"})


@dataclass(kw_only=True)
class AutoRenew(Model):
    """AutoRenew wire fields. Unknown enum strings are preserved."""

    expired: bool = field(metadata={"wire": "expired"})
    quota: bool = field(metadata={"wire": "quota"})
    created_at: str = field(metadata={"wire": "createdAt"})
    expires_at: str = field(metadata={"wire": "expiresAt"})


@dataclass(kw_only=True)
class ApplicationQuota(Model):
    """ApplicationQuota wire fields. Unknown enum strings are preserved."""

    used: int = field(metadata={"wire": "used"})
    max: int | None = field(metadata={"wire": "max"})
    remaining: int | None = field(metadata={"wire": "remaining"})
    total_used: int = field(metadata={"wire": "totalUsed"})


@dataclass(kw_only=True)
class InfoBranch(Model):
    """InfoBranch wire fields. Unknown enum strings are preserved."""

    name: str = field(metadata={"wire": "name"})
    is_active: bool = field(metadata={"wire": "isActive"})
    quota: BranchQuota = field(metadata={"wire": "quota"})


@dataclass(kw_only=True)
class BranchQuota(Model):
    """BranchQuota wire fields. Unknown enum strings are preserved."""

    used: int = field(metadata={"wire": "used"})
    total_used: int = field(metadata={"wire": "totalUsed"})


@dataclass(kw_only=True)
class InfoAccount(Model):
    """InfoAccount wire fields. Unknown enum strings are preserved."""

    email: str = field(metadata={"wire": "email"})
    credit: float = field(metadata={"wire": "credit"})


@dataclass(kw_only=True)
class InfoProduct(Model):
    """InfoProduct wire fields. Unknown enum strings are preserved."""

    name: str = field(metadata={"wire": "name"})


@dataclass(kw_only=True)
class BankSlipResult(Model):
    """BankSlipResult wire fields. Unknown enum strings are preserved."""

    remark: str | UnsetType = field(metadata={"wire": "remark"}, default=UNSET)
    is_duplicate: bool | UnsetType = field(metadata={"wire": "isDuplicate"}, default=UNSET)
    matched_account: MatchedAccount | None | UnsetType = field(
        metadata={"wire": "matchedAccount"}, default=UNSET
    )
    amount_in_order: float | UnsetType = field(metadata={"wire": "amountInOrder"}, default=UNSET)
    amount_in_slip: float = field(metadata={"wire": "amountInSlip"})
    is_amount_matched: bool | UnsetType = field(metadata={"wire": "isAmountMatched"}, default=UNSET)
    raw_slip: BankSlip = field(metadata={"wire": "rawSlip"})


@dataclass(kw_only=True)
class TrueWalletResult(Model):
    """TrueWalletResult wire fields. Unknown enum strings are preserved."""

    remark: str | UnsetType = field(metadata={"wire": "remark"}, default=UNSET)
    is_duplicate: bool | UnsetType = field(metadata={"wire": "isDuplicate"}, default=UNSET)
    matched_account: MatchedAccount | None | UnsetType = field(
        metadata={"wire": "matchedAccount"}, default=UNSET
    )
    amount_in_order: float | UnsetType = field(metadata={"wire": "amountInOrder"}, default=UNSET)
    amount_in_slip: float = field(metadata={"wire": "amountInSlip"})
    is_amount_matched: bool | UnsetType = field(metadata={"wire": "isAmountMatched"}, default=UNSET)
    raw_slip: TrueWalletSlip = field(metadata={"wire": "rawSlip"})


@dataclass(kw_only=True)
class BankSlip(Model):
    """BankSlip wire fields. Unknown enum strings are preserved."""

    payload: str = field(metadata={"wire": "payload"})
    trans_ref: str = field(metadata={"wire": "transRef"})
    date: str = field(metadata={"wire": "date"})
    country_code: str = field(metadata={"wire": "countryCode"})
    amount: SlipAmount = field(metadata={"wire": "amount"})
    fee: float | UnsetType = field(metadata={"wire": "fee"}, default=UNSET)
    ref1: str | UnsetType = field(metadata={"wire": "ref1"}, default=UNSET)
    ref2: str | UnsetType = field(metadata={"wire": "ref2"}, default=UNSET)
    ref3: str | UnsetType = field(metadata={"wire": "ref3"}, default=UNSET)
    sender: SlipParty = field(metadata={"wire": "sender"})
    receiver: SlipReceiver = field(metadata={"wire": "receiver"})


@dataclass(kw_only=True)
class SlipAmount(Model):
    """SlipAmount wire fields. Unknown enum strings are preserved."""

    amount: float = field(metadata={"wire": "amount"})
    local: LocalAmount = field(metadata={"wire": "local"})


@dataclass(kw_only=True)
class LocalAmount(Model):
    """LocalAmount wire fields. Unknown enum strings are preserved."""

    amount: float | UnsetType = field(metadata={"wire": "amount"}, default=UNSET)
    currency: str | UnsetType = field(metadata={"wire": "currency"}, default=UNSET)


@dataclass(kw_only=True)
class SlipReceiver(Model):
    """SlipReceiver wire fields. Unknown enum strings are preserved."""

    bank: SlipReceiverBank | UnsetType = field(metadata={"wire": "bank"}, default=UNSET)
    account: SlipReceiverAccount = field(metadata={"wire": "account"})
    merchant_id: str | None | UnsetType = field(metadata={"wire": "merchantId"}, default=UNSET)


@dataclass(kw_only=True)
class SlipReceiverBank(Model):
    """SlipReceiverBank wire fields. Unknown enum strings are preserved."""

    id: str | UnsetType = field(metadata={"wire": "id"}, default=UNSET)
    name: str | UnsetType = field(metadata={"wire": "name"}, default=UNSET)
    short: str | UnsetType = field(metadata={"wire": "short"}, default=UNSET)


@dataclass(kw_only=True)
class SlipReceiverAccount(Model):
    """SlipReceiverAccount wire fields. Unknown enum strings are preserved."""

    name: SlipReceiverAccountName = field(metadata={"wire": "name"})
    bank: AccountNumber | UnsetType = field(metadata={"wire": "bank"}, default=UNSET)
    proxy: AccountNumber | UnsetType = field(metadata={"wire": "proxy"}, default=UNSET)


@dataclass(kw_only=True)
class SlipReceiverAccountName(Model):
    """SlipReceiverAccountName wire fields. Unknown enum strings are preserved."""

    th: str | UnsetType = field(metadata={"wire": "th"}, default=UNSET)
    en: str | UnsetType = field(metadata={"wire": "en"}, default=UNSET)


@dataclass(kw_only=True)
class SlipParty(Model):
    """SlipParty wire fields. Unknown enum strings are preserved."""

    bank: SlipBank | UnsetType = field(metadata={"wire": "bank"}, default=UNSET)
    account: SlipAccount = field(metadata={"wire": "account"})


@dataclass(kw_only=True)
class SlipBank(Model):
    """SlipBank wire fields. Unknown enum strings are preserved."""

    id: str | UnsetType = field(metadata={"wire": "id"}, default=UNSET)
    name: str | UnsetType = field(metadata={"wire": "name"}, default=UNSET)
    short: str | UnsetType = field(metadata={"wire": "short"}, default=UNSET)


@dataclass(kw_only=True)
class SlipAccount(Model):
    """SlipAccount wire fields. Unknown enum strings are preserved."""

    name: AccountName = field(metadata={"wire": "name"})
    bank: AccountNumber | UnsetType = field(metadata={"wire": "bank"}, default=UNSET)
    proxy: AccountNumber | UnsetType = field(metadata={"wire": "proxy"}, default=UNSET)


@dataclass(kw_only=True)
class AccountName(Model):
    """AccountName wire fields. Unknown enum strings are preserved."""

    th: str | UnsetType = field(metadata={"wire": "th"}, default=UNSET)
    en: str | UnsetType = field(metadata={"wire": "en"}, default=UNSET)


@dataclass(kw_only=True)
class AccountNumber(Model):
    """AccountNumber wire fields. Unknown enum strings are preserved."""

    type: str = field(metadata={"wire": "type"})
    account: str = field(metadata={"wire": "account"})


@dataclass(kw_only=True)
class MatchedAccount(Model):
    """MatchedAccount wire fields. Unknown enum strings are preserved."""

    bank: MatchedBank = field(metadata={"wire": "bank"})
    name_th: str = field(metadata={"wire": "nameTh"})
    name_en: str = field(metadata={"wire": "nameEn"})
    type: str = field(metadata={"wire": "type"})
    bank_number: str = field(metadata={"wire": "bankNumber"})


@dataclass(kw_only=True)
class MatchedBank(Model):
    """MatchedBank wire fields. Unknown enum strings are preserved."""

    name_th: str | UnsetType = field(metadata={"wire": "nameTh"}, default=UNSET)
    name_en: str | UnsetType = field(metadata={"wire": "nameEn"}, default=UNSET)
    code: str | UnsetType = field(metadata={"wire": "code"}, default=UNSET)
    short_code: str | UnsetType = field(metadata={"wire": "shortCode"}, default=UNSET)


@dataclass(kw_only=True)
class TrueWalletSlip(Model):
    """TrueWalletSlip wire fields. Unknown enum strings are preserved."""

    transaction_id: str = field(metadata={"wire": "transactionId"})
    date: str = field(metadata={"wire": "date"})
    amount: float = field(metadata={"wire": "amount"})
    sender: TrueWalletSender = field(metadata={"wire": "sender"})
    receiver: TrueWalletReceiver = field(metadata={"wire": "receiver"})


@dataclass(kw_only=True)
class TrueWalletSender(Model):
    """TrueWalletSender wire fields. Unknown enum strings are preserved."""

    name: str = field(metadata={"wire": "name"})


@dataclass(kw_only=True)
class TrueWalletReceiver(Model):
    """TrueWalletReceiver wire fields. Unknown enum strings are preserved."""

    name: str = field(metadata={"wire": "name"})
    phone: str = field(metadata={"wire": "phone"})


@dataclass(kw_only=True)
class Bank(Model):
    """Bank wire fields. Unknown enum strings are preserved."""

    code: str = field(metadata={"wire": "code"})
    name_th: str = field(metadata={"wire": "nameTh"})
    name_en: str = field(metadata={"wire": "nameEn"})
    short_code: str = field(metadata={"wire": "shortCode"})
    swift_code: str = field(metadata={"wire": "swiftCode"})
    extra_verify: list[ExtraVerifyOption] | None = field(metadata={"wire": "extraVerify"})


@dataclass(kw_only=True)
class ExtraVerifyOption(Model):
    """ExtraVerifyOption wire fields. Unknown enum strings are preserved."""

    value: str = field(metadata={"wire": "value"})
    label: str = field(metadata={"wire": "label"})


@dataclass(kw_only=True)
class BankAccount(Model):
    """BankAccount wire fields. Unknown enum strings are preserved."""

    id: int = field(metadata={"wire": "id"})
    bank_code: str = field(metadata={"wire": "bankCode"})
    bank_number: str = field(metadata={"wire": "bankNumber"})
    name_th: str = field(metadata={"wire": "nameTh"})
    name_en: str = field(metadata={"wire": "nameEn"})
    type: str = field(metadata={"wire": "type"})
    extra_verify: str | None = field(metadata={"wire": "extraVerify"})
    match_mode: str | None = field(metadata={"wire": "matchMode"})
    created_at: str = field(metadata={"wire": "createdAt"})
    updated_at: str = field(metadata={"wire": "updatedAt"})
    deleted_at: str | None = field(metadata={"wire": "deletedAt"})


@dataclass(kw_only=True)
class BankAccountPage(Model):
    """BankAccountPage wire fields. Unknown enum strings are preserved."""

    items: list[BankAccount] = field(metadata={"wire": "items"})
    total: int = field(metadata={"wire": "total"})
    page: int = field(metadata={"wire": "page"})
    limit: int = field(metadata={"wire": "limit"})


@dataclass(kw_only=True)
class LinkResult(Model):
    """LinkResult wire fields. Unknown enum strings are preserved."""

    linked: bool = field(metadata={"wire": "linked"})


@dataclass(kw_only=True)
class UnlinkResult(Model):
    """UnlinkResult wire fields. Unknown enum strings are preserved."""

    unlinked: bool = field(metadata={"wire": "unlinked"})


@dataclass(kw_only=True)
class JobSubmission(Model):
    """JobSubmission wire fields. Unknown enum strings are preserved."""

    job_id: str = field(metadata={"wire": "jobId"})


@dataclass(kw_only=True)
class BatchSubmission(Model):
    """BatchSubmission wire fields. Unknown enum strings are preserved."""

    batch_id: str = field(metadata={"wire": "batchId"})
    jobs: list[BatchJob] = field(metadata={"wire": "jobs"})


@dataclass(kw_only=True)
class BatchJob(Model):
    """BatchJob wire fields. Unknown enum strings are preserved."""

    job_id: str = field(metadata={"wire": "jobId"})
    index: int = field(metadata={"wire": "index"})


@dataclass(kw_only=True)
class Job(Model):
    """Job wire fields. Unknown enum strings are preserved."""

    job_id: str = field(metadata={"wire": "jobId"})
    batch_id: str | UnsetType = field(metadata={"wire": "batchId"}, default=UNSET)
    status: str = field(metadata={"wire": "status"})
    result: JobResult | UnsetType = field(metadata={"wire": "result"}, default=UNSET)
    error: JobError | UnsetType = field(metadata={"wire": "error"}, default=UNSET)
    attempts: int = field(metadata={"wire": "attempts"})
    created_at: str = field(metadata={"wire": "createdAt"})
    updated_at: str = field(metadata={"wire": "updatedAt"})
    branch_id: int | UnsetType = field(metadata={"wire": "branchId"}, default=UNSET)
    service_id: int | UnsetType = field(metadata={"wire": "serviceId"}, default=UNSET)
    callback_event_id: str | UnsetType = field(metadata={"wire": "callbackEventId"}, default=UNSET)
    callback_protocol: int | UnsetType = field(metadata={"wire": "callbackProtocol"}, default=UNSET)
    callback_delivery: CallbackDelivery | UnsetType = field(
        metadata={"wire": "callbackDelivery"}, default=UNSET
    )


@dataclass(kw_only=True)
class JobResult(Model):
    """JobResult wire fields. Unknown enum strings are preserved."""

    status: str = field(metadata={"wire": "status"})
    data: BankSlipResult | None = field(metadata={"wire": "data"})


@dataclass(kw_only=True)
class JobError(Model):
    """JobError wire fields. Unknown enum strings are preserved."""

    code: str | UnsetType = field(metadata={"wire": "code"}, default=UNSET)
    message: str | UnsetType = field(metadata={"wire": "message"}, default=UNSET)
    webhook: str | UnsetType = field(metadata={"wire": "webhook"}, default=UNSET)
    url: str | UnsetType = field(metadata={"wire": "url"}, default=UNSET)
    status: int | UnsetType = field(metadata={"wire": "status"}, default=UNSET)
    at: str | UnsetType = field(metadata={"wire": "at"}, default=UNSET)


@dataclass(kw_only=True)
class CallbackDelivery(Model):
    """CallbackDelivery wire fields. Unknown enum strings are preserved."""

    state: str | None = field(metadata={"wire": "state"})
    http_status: int | None = field(metadata={"wire": "httpStatus"})


@dataclass(kw_only=True)
class WebhookEvent(Model):
    """WebhookEvent wire fields. Unknown enum strings are preserved."""

    job_id: str = field(metadata={"wire": "jobId"})
    batch_id: str | None = field(metadata={"wire": "batchId"})
    status: str = field(metadata={"wire": "status"})
    data: BankSlipResult | None = field(metadata={"wire": "data"})
    error: WebhookError | UnsetType = field(metadata={"wire": "error"}, default=UNSET)
    timestamp: str = field(metadata={"wire": "timestamp"})


@dataclass(kw_only=True)
class WebhookError(Model):
    """WebhookError wire fields. Unknown enum strings are preserved."""

    code: str = field(metadata={"wire": "code"})
    message: str = field(metadata={"wire": "message"})


@dataclass(kw_only=True)
class V1Me(Model):
    """V1Me wire fields. Unknown enum strings are preserved."""

    application: str = field(metadata={"wire": "application"})
    used_quota: int = field(metadata={"wire": "usedQuota"})
    max_quota: int | None = field(metadata={"wire": "maxQuota"})
    remaining_quota: int | None = field(metadata={"wire": "remainingQuota"})
    expired_at: str | None = field(metadata={"wire": "expiredAt"})
    current_credit: float = field(metadata={"wire": "currentCredit"})


@dataclass(kw_only=True)
class QrCode(Model):
    """QrCode wire fields. Unknown enum strings are preserved."""

    image: str = field(metadata={"wire": "image"})
    mime: str = field(metadata={"wire": "mime"})
    payload: str = field(metadata={"wire": "payload"})

    def image_bytes(self) -> bytes:
        """Decode the base64 PNG image."""
        return base64.b64decode(self.image, validate=True)


@dataclass(kw_only=True)
class VerifyOptions(Model):
    """VerifyOptions wire fields. Unknown enum strings are preserved."""

    remark: str | UnsetType = field(metadata={"wire": "remark"}, default=UNSET)
    match_account: bool | UnsetType = field(metadata={"wire": "matchAccount"}, default=UNSET)
    match_amount: float | UnsetType = field(metadata={"wire": "matchAmount"}, default=UNSET)
    check_duplicate: bool | UnsetType = field(metadata={"wire": "checkDuplicate"}, default=UNSET)


@dataclass(kw_only=True)
class CreateBankAccountParams(Model):
    """CreateBankAccountParams wire fields. Unknown enum strings are preserved."""

    bank_code: str = field(metadata={"wire": "bankCode"})
    bank_number: str = field(metadata={"wire": "bankNumber"})
    name_th: str = field(metadata={"wire": "nameTh"})
    name_en: str = field(metadata={"wire": "nameEn"})
    type: AccountType = field(metadata={"wire": "type"})
    extra_verify: str | UnsetType = field(metadata={"wire": "extraVerify"}, default=UNSET)
    match_mode: str | UnsetType = field(metadata={"wire": "matchMode"}, default=UNSET)


@dataclass(kw_only=True)
class UpdateBankAccountParams(Model):
    """UpdateBankAccountParams wire fields. Unknown enum strings are preserved."""

    bank_code: str | UnsetType = field(metadata={"wire": "bankCode"}, default=UNSET)
    bank_number: str | UnsetType = field(metadata={"wire": "bankNumber"}, default=UNSET)
    name_th: str | UnsetType = field(metadata={"wire": "nameTh"}, default=UNSET)
    name_en: str | UnsetType = field(metadata={"wire": "nameEn"}, default=UNSET)
    type: AccountType | UnsetType = field(metadata={"wire": "type"}, default=UNSET)
    extra_verify: str | None | UnsetType = field(metadata={"wire": "extraVerify"}, default=UNSET)
    match_mode: str | UnsetType = field(metadata={"wire": "matchMode"}, default=UNSET)


@dataclass(kw_only=True)
class BatchSlip(Model):
    """BatchSlip wire fields. Unknown enum strings are preserved."""

    remark: str | UnsetType = field(metadata={"wire": "remark"}, default=UNSET)
    match_account: bool | UnsetType = field(metadata={"wire": "matchAccount"}, default=UNSET)
    match_amount: float | UnsetType = field(metadata={"wire": "matchAmount"}, default=UNSET)
    check_duplicate: bool | UnsetType = field(metadata={"wire": "checkDuplicate"}, default=UNSET)
    payload: str = field(metadata={"wire": "payload"})


@dataclass(kw_only=True)
class AsyncVerifyOptions(Model):
    """AsyncVerifyOptions wire fields. Unknown enum strings are preserved."""

    remark: str | UnsetType = field(metadata={"wire": "remark"}, default=UNSET)
    match_account: bool | UnsetType = field(metadata={"wire": "matchAccount"}, default=UNSET)
    match_amount: float | UnsetType = field(metadata={"wire": "matchAmount"}, default=UNSET)
    check_duplicate: bool | UnsetType = field(metadata={"wire": "checkDuplicate"}, default=UNSET)
    callback_url: str | UnsetType = field(metadata={"wire": "callbackUrl"}, default=UNSET)


@dataclass(kw_only=True)
class BatchOptions(Model):
    """BatchOptions wire fields. Unknown enum strings are preserved."""

    callback_url: str | UnsetType = field(metadata={"wire": "callbackUrl"}, default=UNSET)


@dataclass(kw_only=True)
class V1VerifyOptions(Model):
    """V1VerifyOptions wire fields. Unknown enum strings are preserved."""

    check_duplicate: bool | UnsetType = field(metadata={"wire": "checkDuplicate"}, default=UNSET)


@dataclass(kw_only=True)
class ListBankAccountsParams(Model):
    """ListBankAccountsParams wire fields. Unknown enum strings are preserved."""

    type: AccountType | UnsetType = field(metadata={"wire": "type"}, default=UNSET)
    bank_code: str | UnsetType = field(metadata={"wire": "bankCode"}, default=UNSET)
    page: int | UnsetType = field(metadata={"wire": "page"}, default=UNSET)
    limit: int | UnsetType = field(metadata={"wire": "limit"}, default=UNSET)


@dataclass(kw_only=True)
class QrRequest(Model):
    """QrRequest wire fields. Unknown enum strings are preserved.

    One flat model for every `type`; the API checks the combinations. With `biller_id`, `ref1`
    is optional and `ref2` needs `ref1`. KSHOP `ref1` is the shop id KB + 12 digits, MAE_MANEE
    `ref1` the 15-digit shop id. TUNGNGERN needs `merchant_name`, the English shop name. Fields
    are sent as given.
    """

    type: QrType = field(metadata={"wire": "type"})
    msisdn: str | UnsetType = field(metadata={"wire": "msisdn"}, default=UNSET)
    nat_id: str | UnsetType = field(metadata={"wire": "natId"}, default=UNSET)
    e_wallet_id: str | UnsetType = field(metadata={"wire": "eWalletId"}, default=UNSET)
    biller_id: str | UnsetType = field(metadata={"wire": "billerId"}, default=UNSET)
    ref1: str | UnsetType = field(metadata={"wire": "ref1"}, default=UNSET)
    ref2: str | UnsetType = field(metadata={"wire": "ref2"}, default=UNSET)
    amount: float | UnsetType = field(metadata={"wire": "amount"}, default=UNSET)
    merchant_name: str | UnsetType = field(metadata={"wire": "merchantName"}, default=UNSET)


@dataclass(kw_only=True)
class RateLimit(Model):
    """RateLimit wire fields. Unknown enum strings are preserved."""

    limit: int = field(metadata={"wire": "limit"})
    remaining: int = field(metadata={"wire": "remaining"})
    reset: int = field(metadata={"wire": "reset"})


@dataclass(kw_only=True)
class ResponseMeta(Model):
    """ResponseMeta wire fields. Unknown enum strings are preserved."""

    status: int = field(metadata={"wire": "status"})
    request_id: str | None = field(metadata={"wire": "requestId"})
    message: str | None = field(metadata={"wire": "message"})
    rate_limit: RateLimit | None = field(metadata={"wire": "rateLimit"})
    headers: dict[str, str] = field(metadata={"wire": "headers"})


@dataclass(kw_only=True)
class BankList(Model):
    """Iterable bank catalog, serialized as a plain array."""

    items: list[Bank]

    def __iter__(self) -> Iterator[Bank]:
        return iter(self.items)

    def __len__(self) -> int:
        return len(self.items)

    def to_dict(self) -> list[Any]:
        return [encode(item) for item in self.items]
