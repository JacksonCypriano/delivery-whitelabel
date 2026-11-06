// Presentation helpers ported from the existing merchant JavaScript.
export function digits(value: string) {
  return String(value || "").replace(/\D/g, "");
}

export function formatWhatsapp(value: string) {
  var d = digits(value).slice(0, 13);
  if (!d) return "";
  if (d.indexOf("55") !== 0 && d.length <= 11) d = "55" + d;
  if (d.length <= 2) return "+" + d;
  var country = d.slice(0, 2);
  var area = d.slice(2, 4);
  var number = d.slice(4);
  var result = "+" + country;
  if (area) result += " (" + area + ")";
  if (number) {
    if (number.length <= 4) result += " " + number;
    else if (number.length <= 8)
      result += " " + number.slice(0, 4) + "-" + number.slice(4);
    else result += " " + number.slice(0, 5) + "-" + number.slice(5, 9);
  }
  return result;
}

export function normalizeTime(value: string) {
  var raw = String(value || "").trim();
  if (!raw) return "";

  var onlyDigits = digits(raw).slice(0, 4);
  var hour: number;
  var minute: number;

  if (raw.indexOf(":") >= 0) {
    var parts = raw.split(":");
    hour = parseInt(parts[0], 10);
    minute = parts.length > 1 && parts[1] !== "" ? parseInt(parts[1], 10) : 0;
  } else if (onlyDigits.length <= 2) {
    hour = parseInt(onlyDigits, 10);
    minute = 0;
  } else if (onlyDigits.length === 3) {
    hour = parseInt(onlyDigits.slice(0, 1), 10);
    minute = parseInt(onlyDigits.slice(1), 10);
  } else {
    hour = parseInt(onlyDigits.slice(0, 2), 10);
    minute = parseInt(onlyDigits.slice(2), 10);
  }

  if (
    !Number.isFinite(hour) ||
    !Number.isFinite(minute) ||
    hour < 0 ||
    hour > 23 ||
    minute < 0 ||
    minute > 59
  ) {
    return raw;
  }

  return String(hour).padStart(2, "0") + ":" + String(minute).padStart(2, "0");
}

export function digitsOnly(value: string) {
  return String(value || "").replace(/\D/g, "");
}

export function documentChars(value: string) {
  return String(value || "")
    .toUpperCase()
    .replace(/[^0-9A-Z]/g, "")
    .slice(0, 14);
}

export function formatDocument(value: string) {
  var raw = documentChars(value);
  if (raw.length <= 11 && /^\d*$/.test(raw)) {
    var cpf = raw;
    if (cpf.length > 9)
      return (
        cpf.slice(0, 3) +
        "." +
        cpf.slice(3, 6) +
        "." +
        cpf.slice(6, 9) +
        "-" +
        cpf.slice(9)
      );
    if (cpf.length > 6)
      return cpf.slice(0, 3) + "." + cpf.slice(3, 6) + "." + cpf.slice(6);
    if (cpf.length > 3) return cpf.slice(0, 3) + "." + cpf.slice(3);
    return cpf;
  }
  if (raw.length > 12)
    return (
      raw.slice(0, 2) +
      "." +
      raw.slice(2, 5) +
      "." +
      raw.slice(5, 8) +
      "/" +
      raw.slice(8, 12) +
      "-" +
      raw.slice(12)
    );
  if (raw.length > 8)
    return (
      raw.slice(0, 2) +
      "." +
      raw.slice(2, 5) +
      "." +
      raw.slice(5, 8) +
      "/" +
      raw.slice(8)
    );
  if (raw.length > 5)
    return raw.slice(0, 2) + "." + raw.slice(2, 5) + "." + raw.slice(5);
  if (raw.length > 2) return raw.slice(0, 2) + "." + raw.slice(2);
  return raw;
}

export function brazilianPhoneDigits(value: string) {
  var digits = digitsOnly(value);
  if (
    digits.indexOf("55") === 0 &&
    (digits.length === 12 || digits.length === 13)
  ) {
    digits = digits.slice(2);
  }
  return digits.slice(0, 11);
}

export function formatPhone(value: string) {
  var digits = brazilianPhoneDigits(value);
  if (digits.length > 10) {
    return (
      "(" +
      digits.slice(0, 2) +
      ") " +
      digits.slice(2, 7) +
      "-" +
      digits.slice(7)
    );
  }
  if (digits.length > 6) {
    return (
      "(" +
      digits.slice(0, 2) +
      ") " +
      digits.slice(2, 6) +
      "-" +
      digits.slice(6)
    );
  }
  if (digits.length > 2)
    return "(" + digits.slice(0, 2) + ") " + digits.slice(2);
  if (digits.length) return "(" + digits;
  return "";
}
