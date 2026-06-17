document.addEventListener("alpine:init", () => {
  Alpine.data("changePasswordPage", () => ({
    currentPassword: "",
    newPassword: "",
    confirmPassword: "",
    loading: false,
    error: "",

    init() {
      if (!isAuthenticated()) {
        window.location.href = "login.html";
        return;
      }
      if (!mustChangePassword()) {
        redirectAfterLogin({
          role: getRole(),
          username: getUsername(),
          must_change_password: false,
        });
      }
    },

    async submit() {
      this.error = "";
      if (!this.newPassword || this.newPassword.length < 4) {
        this.error = "Новый пароль должен содержать минимум 4 символа";
        return;
      }
      if (this.newPassword !== this.confirmPassword) {
        this.error = "Подтверждение пароля не совпадает";
        return;
      }

      this.loading = true;
      try {
        const data = await apiRequest("/auth/change-password", "POST", {
          current_password: this.currentPassword,
          new_password: this.newPassword,
        });
        saveAuth(data);
        showToast("Пароль успешно изменён", "success");
        redirectAfterLogin(data);
      } catch (error) {
        this.error = error.message;
        showToast(this.error, "error");
      } finally {
        this.loading = false;
      }
    },
  }));
});
