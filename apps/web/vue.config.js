module.exports = {
  devServer: {
    port: 8080,
    proxy: {
      "/api": { target: "http://localhost:8000", changeOrigin: true },
      "/files": { target: "http://localhost:8000", changeOrigin: true }
    }
  }
};
