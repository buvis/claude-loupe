pub fn parse_port_or_none(raw: &str) -> Option<u16> {
    raw.parse().ok()
}

#[cfg(test)]
mod tests {
    use super::parse_port_or_none;

    #[test]
    fn parses_valid_port() {
        let port: u16 = "80".parse().unwrap();
        assert_eq!(parse_port_or_none("80"), Some(port));
    }
}
