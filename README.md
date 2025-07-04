# Automated downtimes for Checkmk

| ActiveCheck-Plugin for automatically setting downtimes on host/services based on other hosts/service.

### Requirements

- CMK 2.2, 2.3. 2.1 should work but not tested.
- CRE/Raw-edition is sufficent
- Distributed setups are supported

### Releases

See exchange.checkmk.com

### Changes

- 2.0.8:
  - Improve support for macros, also on RAW-Editions. 
  - Introduce Regex-Replace-Support to allow transform content of macros in rules fields.
    Expample:
    `Tunnel (?:{{$HOSTNAME$~~([0-9a-z]+).*~~\1}})`        
    In this sample
    - the preprocessor extracts the content of `{{ }}`
    - it splits the content by `~~` into 3 parts
      - source macro
      - regex to match the source macro and define capture groups
      - output of the capture group(s)
    - for a `$HOSTNAME$`  like `myhost4711.my.domain` the output of `{{ }}` is `myhost4711` 
    - the resulting rule is `Tunnel (?:myhost4711)` which allows to match a tunnel like `Tunnel MYHOST4711`

- 2.0.7: 
  -  Initial support for a gracetime before removing downtimes after prerequisites are no longer met
- 2.0.6:
  - Spread cache refreshes and other cache improvements
- 2.0.5: 
  - Add support for reading the estimated downtime from perfdata.
    In the rule it is required to define service-output-regex (at minimum ".+")
    Then specify the perfdata-names which contain unix-timestamps. 
    See the inline-help!
    Again a 10 minute gracetime before/after the specifed timestamps is added.
  - Fixes for retaining CMK 2.2 compat
2.0.3:
  - Fix param eval for case-insensitive
2.0.2:
  - Improve refreshing of cache in certain circumstances
  - Fixes/Improvements in ruleditor (Thanx to TuneFish41)
  

### Docs

See WIKI on [https://github.com/svalabs/check_mk_automated_downtimes](https://github.com/svalabs/check_mk_automated_downtimes/wiki)

GPL-Licensed


