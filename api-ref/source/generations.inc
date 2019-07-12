.. _generations:

==========================================
Resource Provider and Consumer Generations
==========================================
Placement handles concurrent requests against the same entity by maintaining a
**generation** for resource providers and consumers. The generation is an
opaque value that is updated every time its entity is successfully changed on
the server.

At appropriate microversions, the generation is returned in responses involving
resource providers and/or consumers (allocations), and must be included in
requests which make changes to those entities. The server checks to make sure
the generation specified in the request matches the internal value. A mismatch
indicates that a different request successfully updated that entity in the
interim, thereby changing its generation. This will result in an HTTP 409
Conflict response with `error code <error_codes_>`_
``placement.concurrent_update``.

Depending on the usage scenario, an appropriate reaction to such an error may
be to re-``GET`` the entity in question, re-evaluate and update as appropriate,
and resubmit the request with the new payload.

The following pseudocode is a simplistic example of how one might ensure that a
trait is set on a resource provider.

.. note:: This is not production code. Aside from not being valid syntax for
          any particular programming language, it deliberately glosses over
          details and good programming practices such as error checking, retry
          limits, etc. It is purely for illustrative purposes.

::

 function _is_concurrent_update(resp) {
     if(resp.status_code != 409) return False
     return(resp.json()["errors"][0]["code"] == "placement.concurrent_update")
 }

 function ensure_trait_on_provider(provider_uuid, trait) {
     do {
         path = "/resource_providers/" + provider_uuid + "/traits"
         get_resp = placement.GET(path)
         payload = get_resp.json()
         if(trait in payload["traits"]) return
         payload["traits"].append(trait)
         put_resp = placement.PUT(path, payload)
     } while _is_concurrent_update(put_resp)
 }
