import io
import time
import unittest
import urllib.error
from unittest.mock import patch

import be900_exporter as b


class ProtocolTests(unittest.TestCase):
    def test_soap_payload(self):
        xml = (b'<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">'
               b'<s:Body><u:Reply xmlns:u="test"><NewUptime>42</NewUptime>'
               b'</u:Reply></s:Body></s:Envelope>')
        with patch.object(b, "_read_request", return_value=xml) as request:
            result = b.soap_read("192.0.2.1", b.WAN_IP, "GetStatusInfo")
        self.assertEqual(result, {"NewUptime": "42"})
        self.assertEqual(request.call_args.args[0].get_method(), "POST")

    def test_tdp_recognized(self):
        packet = bytes.fromhex("0100000200001101000003e56b89a97b")
        payload = bytearray()
        for kind, value in [(3,b"TP-Link"),(5,b"Archer BE900"),(9,b"WirelessRouter"),(21,b"Main")]:
            payload += kind.to_bytes(2,"big") + len(value).to_bytes(2,"big") + value
            padding = (-len(payload)) % 4
            if padding:
                payload += bytes([255]) + bytes(padding-1)
        packet = packet + bytes(payload)
        class Socket:
            def __enter__(self): return self
            def __exit__(self,*_): pass
            def settimeout(self,*_): pass
            def sendto(self,*_): pass
            def recvfrom(self,*_): return packet,("192.0.2.1",20002)
        with patch.object(b.socket,"socket",return_value=Socket()):
            info=b.tdp_read("192.0.2.1")
        self.assertEqual(info["model"],"Archer BE900")
        self.assertEqual(info["role"],"Main")

    def test_no_sensitive_labels(self):
        c=b.Collector("192.0.2.1")
        c.values={"be900_upnp_up":1, "be900_tdp_up":1}
        c.info={"manufacturer":"TP-Link","model":"Archer BE900","role":"Main","device_type":"WirelessRouter"}
        c.last_poll=time.monotonic()  # unit test: never contact the live router
        output=c.render().decode()
        self.assertIn("be900_info{",output)
        self.assertNotIn("mac=",output)
        self.assertIn("be900_upnp_up 1",output)

    def test_port_mappings_stop_only_at_713(self):
        def fake_read(ip,service,name,*,timeout=3,params=None):
            index=params["NewPortMappingIndex"]
            if index<2:
                return {"NewLeaseDuration":"0" if index==0 else "120"}
            raise urllib.error.HTTPError("http://x",500,"error",{},
                                         io.BytesIO(b"<errorCode>713</errorCode>"))
        with patch.object(b,"soap_read", side_effect=fake_read):
            self.assertEqual(b.collect_mapping_count("192.0.2.1", 2, 10),(2,1))


if __name__=="__main__":
    unittest.main()
