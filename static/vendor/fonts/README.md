# Local fonts

Inter 4.1: https://github.com/rsms/inter/tree/v4.1/docs/font-files

Roboto: https://github.com/google/fonts/tree/1c627bfa375fc51cf86fabeca4f6e08a95f0aa5c/ofl/roboto

Overpass 4.0: https://github.com/RedHatOfficial/Overpass

Inter and Roboto use the bundled variable files. Overpass uses the same regular, medium, bold and italic files as Media Journal. The bundled fonts include their SIL Open Font License 1.1 notices.

Inter is the default at every screen width. App Font is saved per browser, and the selected web font's upright files preload from the local app.

All map labels follow App Font too. MapLibre renders them through its built-in local font support, using these CSS font faces or the chosen device font. Provider glyph URLs are removed before styles load, so Simple and Adventure have no external font dependency. Changes in Settings update the retained map without rebuilding it.

SHA-256:

- InterVariable-Italic.woff2: `e564f652916db6c139570fefb9524a77c4d48f30c92928de9db19b6b5c7a262a`
- InterVariable.woff2: `693b77d4f32ee9b8bfc995589b5fad5e99adf2832738661f5402f9978429a8e3`
- RobotoVariable-Italic.ttf: `9725a847af6b460ffca162ae66d20dad48b01876137947180b42d7dcd7887182`
- RobotoVariable.ttf: `d7598e12c5dbef095ff8272cfc55da0250bd07fbdecbac8a530b9b277872a134`
- overpass-500.woff2: `bc08d0d19b8d35c70208175a42e9fbf9b092009809e94b3e225cbc6984dece65`
- overpass-500italic.woff2: `84a418cfc937dff169408c2bfe5af500581dd0a6ffedfe038adf315a970078e3`
- overpass-700.woff2: `bf8991cfc730da0ccc82189899e465b0c02ddb7fd6c31a1cfcadd69e3c6533cf`
- overpass-700italic.woff2: `19d6cd6d932126dfb455c3cec16c0c478037bde3dbead2551a21d6fa4c048442`
- overpass-italic.woff2: `52d1975c1f3919cdff29301cdf460667d0840d94c9cc37a7de1d6aa5b636aa3f`
- overpass-regular.woff2: `4db37c73eacc95edeef5f44c822acd8424506821844ab01470667a8ab680ba81`
