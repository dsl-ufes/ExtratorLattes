"""Expected operational failures returned by metric providers."""

class ProviderFailure(Exception):
    status = 'ERRO_TEMPORARIO'
class AuthenticationError(ProviderFailure): status = 'CREDENCIAL_AUSENTE'
class RateLimitError(ProviderFailure): status = 'LIMITE_EXCEDIDO'
class TransportError(ProviderFailure): status = 'ERRO_TEMPORARIO'
class RemoteServerError(ProviderFailure): status = 'ERRO_TEMPORARIO'
class InvalidRemoteResponse(ProviderFailure): status = 'ERRO_PERMANENTE'
class PermanentRequestError(ProviderFailure): status = 'ERRO_PERMANENTE'
