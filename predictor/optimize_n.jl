using Flux
include("../../preprocessor/df_parser.jl")


accs = df_parser.dfToMatrix(df_parser.getdf("./augmented_accs.csv"))

a, b, c, d = rand(1), rand(1), rand(1), rand(1)

predict(x) = (a .* exp.(c .* x .+ d)) ./ (exp.(c .* x .+ d) .+ b)

loss(x, y) = Flux.Losses.mse(predict(x), y)

ps = Flux.params(a, b, c, d)

opt = Adam(.1)
data = Flux.DataLoader((accs[:, begin], accs[:, end]))

for i in 1:100
    Flux.train!(loss, ps, data, opt)
end

scatter(accs[:, begin], accs[:, end], color="blue")
test_range = Float32.(hcat(collect(0:.01:10)))
plot!(test_range, predict(test_range), color="green")

preds = predict(test_range)
optimized_n = 0
for (n, i) in enumerate(preds)
    if round(i; digits=2) >= round(maximum(preds); digits=1)
        optimized_n = Int32(round(test_range[n]))
        break
    end
end

GREEN = "\033[1;32m"
NC = "\033[0m"
println("Optimized amount of augmentations: $(GREEN)$(optimized_n)$(NC)")