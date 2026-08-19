export const winsarpLanguage: any = {
  defaultToken: "invalid",
  ignoreCase: false,

  keywords: [
    "IF", "THEN", "ELSE", "ENDIF", "SET", "RESET", "K", "R", "P", "VF", "VU",
    "CAMPO70", "FIELD", "Z",
  ],

  operators: ["U", "Z", "S", "A", ">", "!"],

  typeKeywords: ["V04", "V05"],

  brackets: [
    { open: "(", close: ")", token: "delimiter.parenthesis" },
  ],

  tokenizer: {
    root: [
      [/V0[45]/, { token: "keyword.type" }],
      [/\b(VF|VU)\b/, { token: "keyword.control" }],
      [/\b(IF|THEN|ELSE|ENDIF)\b/, { token: "keyword.control" }],
      [/\b(SET|RESET|K|CAMPO70|FIELD)\b/, { token: "keyword" }],
      [/\b(R|P)\b/, { token: "keyword.jump" }],
      [/\bZ\b/, { token: "constant" }],
      [/\b\d{2,4}\b/, { token: "number.field" }],
      [/\b\d\b/, { token: "number" }],
      [/"[^"]*"/, { token: "string.double" }],
      [/'[^']*'/, { token: "string.single" }],
      [/[UAS]/, { token: "operator" }],
      [/!(\d+)/, { token: "operator.reset" }],
      [/[()]/, "@brackets"],
      [/\s+/, "white"],
      [/;.*$/, { token: "comment" }],
      [/./, { token: "invalid" }],
    ],
  },
};

export const winsarpTheme: any = {
  base: "vs-dark",
  inherit: true,
  rules: [
    { token: "keyword", foreground: "569CD6", fontStyle: "bold" },
    { token: "keyword.control", foreground: "C586C0", fontStyle: "bold" },
    { token: "keyword.jump", foreground: "DCDCAA", fontStyle: "bold" },
    { token: "keyword.type", foreground: "4EC9B0", fontStyle: "bold" },
    { token: "operator", foreground: "D4D4D4" },
    { token: "operator.reset", foreground: "CE9178" },
    { token: "number", foreground: "B5CEA8" },
    { token: "number.field", foreground: "9CDCFE" },
    { token: "string.double", foreground: "CE9178" },
    { token: "string.single", foreground: "CE9178" },
    { token: "constant", foreground: "569CD6" },
    { token: "comment", foreground: "6A9955", fontStyle: "italic" },
    { token: "delimiter.parenthesis", foreground: "FFD700" },
  ],
  colors: {
    "editor.background": "#111113",
    "editor.foreground": "#D4D4D4",
    "editorLineNumber.foreground": "#4B526D",
    "editor.selectionBackground": "#264F78",
    "editorCursor.foreground": "#569CD6",
  },
};

export const winsarpThemeLight: any = {
  base: "vs",
  inherit: true,
  rules: [
    { token: "keyword", foreground: "0451A5", fontStyle: "bold" },
    { token: "keyword.control", foreground: "AF00DB", fontStyle: "bold" },
    { token: "keyword.jump", foreground: "795E26", fontStyle: "bold" },
    { token: "keyword.type", foreground: "267F99", fontStyle: "bold" },
    { token: "operator", foreground: "383A42" },
    { token: "operator.reset", foreground: "A31515" },
    { token: "number", foreground: "098658" },
    { token: "number.field", foreground: "0451A5" },
    { token: "string.double", foreground: "A31515" },
    { token: "string.single", foreground: "A31515" },
    { token: "constant", foreground: "0451A5" },
    { token: "comment", foreground: "008000", fontStyle: "italic" },
    { token: "delimiter.parenthesis", foreground: "BF8803" },
  ],
  colors: {
    "editor.background": "#FFFFFF",
    "editor.foreground": "#383A42",
    "editorLineNumber.foreground": "#A0A0A0",
    "editor.selectionBackground": "ADD6FF",
    "editorCursor.foreground": "0451A5",
  },
};
