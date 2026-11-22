"""TCP transport for ADB that writes each protocol packet completely."""

from adb_shell.exceptions import TcpTimeoutException
from adb_shell.transport.tcp_transport import TcpTransport


class CompleteTcpTransport(TcpTransport):
    def bulk_write(self, data, transport_timeout_s):
        # adb-shell ignores the returned byte count, while socket.send can
        # accept only part of the packet when the TCP buffer is under pressure.
        connection = self._connection
        previous_timeout = connection.gettimeout()
        connection.settimeout(transport_timeout_s)
        try:
            connection.sendall(data)
        except TimeoutError as err:
            raise TcpTimeoutException("Timed out sending an ADB packet") from err
        finally:
            connection.settimeout(previous_timeout)
        return len(data)
