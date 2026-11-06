require ["fileinto", "mailbox"];

# Install only behind a trusted filtering path that strips sender-supplied
# X-Clef-* headers. Observe-only classifications never set action=junk.
if header :is "X-Clef-Action" "junk" {
    fileinto :create "Junk";
    stop;
}
