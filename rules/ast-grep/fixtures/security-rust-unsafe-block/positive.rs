pub fn read_raw(ptr: *const u32) -> u32 {
    unsafe { *ptr }
}
