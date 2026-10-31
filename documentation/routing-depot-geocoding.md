# Depot Geocoding Handoff

The modeled route depot is `stadtreinigung-basel`:

```text
Stadtreinigung (SR)
Brüssel-Strasse 22
4053 Basel, Switzerland
```

`code/routing/src/smart_bin_routing/adapters/depot_geocoding.py` provides a
deliberate one-shot Nominatim lookup and an offline accepted-record loader. It
uses structured address parameters, `countrycodes=ch`, address details, a
descriptive User-Agent, and one-request-per-second pacing. It never performs a
request during import, planning, or record loading.

No live lookup has been executed and no coordinates have been accepted in this
repository. The address is not evidence of a vehicle entrance or unloading
permission; persisted records always retain `vehicle_access_confirmed: false`.

## Commands

From `code/routing/`, a live lookup requires explicit approval and a
descriptive identifying value:

The command displays all candidates and prompts for an exact reviewed
candidate. The selection is bound to that same response; it does not fetch
again:

```text
uv run python -m smart_bin_routing.adapters.depot_geocoding lookup \
  --output /path/to/stadtreinigung-basel.json \
  --user-agent "smart-trash-routing/0.1 (contact@example.org)"
```

For scripted review, `--select N` performs the explicit selection from the
candidate list returned by that same request.

Inspecting an accepted record is offline:

```text
uv run python -m smart_bin_routing.adapters.depot_geocoding inspect \
  /path/to/stadtreinigung-basel.json
```

The record is an address point only. A future geographic provider will load it,
perform explicit road-network snapping, and produce the directed
`TravelCostMatrix` consumed by the existing `plan_collection(...)` flow.
Coordinates are not passed directly to the matrix optimizer.

The public Nominatim service requires attribution, caching, a descriptive
User-Agent or Referer, and no more than one request per second. Separate
invocations must also respect that service-wide limit. See the official
[Search API](https://nominatim.org/release-docs/latest/api/Search/) and
[Usage Policy](https://operations.osmfoundation.org/policies/nominatim/).
