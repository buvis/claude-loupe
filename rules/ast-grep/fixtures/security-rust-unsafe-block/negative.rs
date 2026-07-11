pub fn read_safe(values: &[u32]) -> Option<u32> {
    values.first().copied()
}
